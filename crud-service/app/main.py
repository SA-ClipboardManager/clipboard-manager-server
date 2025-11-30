import asyncio
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Literal, Any

import aiofiles
import aiomysql
from PIL import Image

from fastapi import FastAPI, Form, HTTPException, Depends, status, File, UploadFile, Request
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis
import aio_pika

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

# --------------------------------------------------------------------------
# 1. 설정 및 로깅
# --------------------------------------------------------------------------
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

class Settings(BaseSettings):
    db_host: str = "crud-mysql-db"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str 
    db_name: str = "crud_db"
    redis_url: str = "redis://crud-redis-cache:6379"
    
    # RabbitMQ 설정
    rabbitmq_host: str = "rabbitmq-broker"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = Field(..., alias="RABBITMQ_USER")
    rabbitmq_password: str = Field(..., alias="RABBITMQ_PASS")
    token_verify_queue: str = "token_verify_queue"
    token_verify_response_queue: str = "token_verify_response_queue"
    
    # JWT 설정 (로그인 서비스와 동일한 키 필요)
    secret_key: str = "your-secret-key-here"  # 실제로는 환경변수로 설정해야 함
    algorithm: str = "HS256"
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

settings = Settings()


# --------------------------------------------------------------------------
# Database Connection with Retry Logic
# --------------------------------------------------------------------------
async def create_db_pool():
    retries = 15  # 최대 15번 시도
    delay = 2  # 2초 간격 (총 30초 대기)
    
    for i in range(retries):
        try:
            logger.info(f"Attempting to connect to DB host: {settings.db_host}")
            pool = await aiomysql.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                db=settings.db_name,
                autocommit=True,
            )
            logger.info(f" CRUD Database Connected successfully (Attempt {i+1}")
            return pool
        except Exception as e:
            logger.warning(f" CRUD DB not ready (Attempt {i+1}/{retries}). Retrying in {delay}s...")
            await asyncio.sleep(delay)
    
    # 반복문이 끝나도 연결 안 되면 에러 발생
    raise ConnectionError(" Failed to connect to CRUD Database after multiple retries.")# --------------------------------------------------------------------------
# 2. Pydantic Models
# --------------------------------------------------------------------------

class ItemCreate(BaseModel):
    id: str
    content: Optional[str] = None
    type: Literal["txt", "img"]
    format: str
    created_at: int
    # Tag Service 분리로 인해 CRUD는 태그를 저장하지 않지만, 이벤트 발행용으로 받음
    tags: Optional[List[Any]] = []

class ItemResponse(ItemCreate):
    pass

class ImageMetaResponse(BaseModel):
    width: int
    height: int
    file_size: int
    file_path: str
    thumbnail_path: Optional[str]

class ClipboardDataResponse(BaseModel):
    id: str
    user_id: str
    type: str
    format: str
    content: str
    created_at: int
    image_meta: Optional[ImageMetaResponse] = None
    tags: List[Any] = [] # 반환 시 빈 리스트 (Tag Service 담당)

# 동기화 이벤트 모델
class SyncEventItem(BaseModel):
    operation: Literal["INSERT", "UPDATE", "DELETE"]
    data_id: str
    args: Dict[str, Any] # [FIX] Any 사용됨
    correlation_id: str
    local_outbox_id: int

class SyncResponse(BaseModel):
    success: bool
    processed_count: int
    tag_mappings: List[Dict[str, str]] = []


# --------------------------------------------------------------------------
# 3. App State & DB Init
# --------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.db_pool = None
        self.redis = None
        self.rabbitmq_connection = None

app_state = AppState()

# Tag 관련 테이블 제거, User FK 제거
CREATE_TABLES = """
    CREATE TABLE IF NOT EXISTS clipboard (
        id VARCHAR(36) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        type ENUM('img', 'txt') NOT NULL,
        format VARCHAR(50) NOT NULL,
        content LONGTEXT,
        created_at BIGINT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS image_meta (
        data_id VARCHAR(36) PRIMARY KEY,
        width INTEGER,
        height INTEGER,
        file_size INTEGER,
        file_path TEXT NOT NULL,
        thumbnail_path TEXT,
        FOREIGN KEY (data_id) REFERENCES clipboard(id) ON DELETE CASCADE
    );
"""

async def initialize_database():
    async with app_state.db_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                for statement in CREATE_TABLES.strip().split(';'):
                    if statement.strip():
                        await cursor.execute(statement.strip() + ';')
                await conn.commit()
                logger.info("CRUD Database initialized.")
            except Exception as e:
                logger.error(f"DB Init Failed: {e}")

async def publish_event(topic: str, data: Dict):
    """실제 RabbitMQ 이벤트 발행 로직"""
    if not app_state.rabbitmq_connection:
        logger.error("RabbitMQ connection not available.")
        return

    channel = app_state.rabbitmq_connection
    try:
        # 'notifications' exchange를 fanout으로 선언 (수신측과 동일해야 함)
        exchange = await channel.declare_exchange("notifications", aio_pika.ExchangeType.FANOUT)

        # 메시지 생성
        message_body = {
            "event": topic,
            "data": data,
            # user_id는 data 딕셔너리 안에 이미 포함되어 있어야 함
            "user_id": data.get("user_id") 
        }
        
        message = aio_pika.Message(
            body=json.dumps(message_body).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        # Fanout exchange에 메시지 발행 (routing_key는 무시됨)
        await exchange.publish(message, routing_key="")
        logger.info(f"[MQ Sent] Event: {topic}, User: {data.get('user_id')}")

    except Exception as e:
        logger.error(f"Failed to publish RabbitMQ event: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Initialize database connection pool
        app_state.db_pool = await create_db_pool()
        app_state.redis = Redis.from_url(settings.redis_url)
        await FastAPILimiter.init(app_state.redis)
        await initialize_database()
        
        # RabbitMQ 연결
        rabbitmq_url = (
            f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}@"
            f"{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
        )
        
        connection = None
        for i in range(15): # Retry for 30 seconds
            try:
                connection = await aio_pika.connect_robust(rabbitmq_url)
                app_state.rabbitmq_connection = await connection.channel()
                logger.info("Successfully connected to RabbitMQ.")
                break
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"RabbitMQ not ready, retrying... (attempt {i+1}/15)")
                if i == 14:
                    logger.error("Could not connect to RabbitMQ after multiple retries.")
                    raise e
                await asyncio.sleep(2)


        logger.info("CRUD Service Started")
        yield
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise
    finally:
        if app_state.db_pool:
            app_state.db_pool.close()
            await app_state.db_pool.wait_closed()
        if app_state.redis:
            await app_state.redis.close()
        # RabbitMQ 연결 종료
        if app_state.rabbitmq_connection and not app_state.rabbitmq_connection.is_closed:
            await app_state.rabbitmq_connection.close()
            if app_state.rabbitmq_connection.connection:
                await app_state.rabbitmq_connection.connection.close()
            logger.info("RabbitMQ connection closed.")

app = FastAPI(lifespan=lifespan) 

# 정적 파일 경로
UPLOAD_DIR = "uploads"
original_dir = os.path.join(UPLOAD_DIR, "original")
thumbnail_dir = os.path.join(UPLOAD_DIR, "thumbnail")
os.makedirs(original_dir, exist_ok=True)
os.makedirs(thumbnail_dir, exist_ok=True)

app.mount("/local/original", StaticFiles(directory=original_dir), name="original-images")
app.mount("/local/thumbnail", StaticFiles(directory=thumbnail_dir), name="thumbnail-images")


# --------------------------------------------------------------------------
# 4. Dependencies & Utils
# --------------------------------------------------------------------------
async def get_db():
    async with app_state.db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            yield conn, cursor

async def get_current_user(request: Request):
    """Gateway Offloading: 헤더에서 User ID 신뢰"""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        logger.warning("Direct access without Gateway Header.")
        return {"user_id": "test-user"} 
    return {"user_id": user_id}

def delete_local_file(url_path: str, base_dir: str):
    if not url_path: return
    filename = os.path.basename(url_path)
    abs_path = os.path.join(base_dir, filename)
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
        except Exception:
            pass

# --------------------------------------------------------------------------
# [Helper] DB Save Logic
# --------------------------------------------------------------------------
async def _save_clipboard_item(cursor, item_data: dict, user_id: str):
    """
    DB 저장 로직을 한곳으로 모음 (DRY 원칙 적용)
    /sync/events 와 /api/v1/items 에서 공통 사용
    """
    if not all(k in item_data for k in ('id', 'type', 'format', 'created_at')):
        logger.warning(f"Missing fields: {item_data.keys()}")
        return

    content = item_data.get('content')

    await cursor.execute("""
        INSERT INTO clipboard (id, user_id, content, type, format, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            content=VALUES(content), 
            created_at=VALUES(created_at)
    """, (
        item_data['id'], user_id, content, 
        item_data['type'], item_data['format'], item_data['created_at']
    ))


# ----------------------------------------------------------------------
# API Endpoints
# ----------------------------------------------------------------------

@app.post("/sync/events", response_model=SyncResponse)
async def handle_sync_events(
    events: List[SyncEventItem],
    user: Dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    [메인 엔드포인트] 클라이언트 Outbox 동기화 처리
    """
    conn, cursor = db
    user_id = user["user_id"]
    processed_count = 0

    try:
        await conn.begin()
        
        for event in events:
            if event.operation in ["INSERT", "UPDATE"]:
                await _save_clipboard_item(cursor, event.args, user_id)

                # 태그 이벤트 발행
                if "tags" in event.args and event.args["tags"]:
                     await publish_event("clip_synced_tags", {
                        "data_id": event.args.get("id"), 
                        "user_id": user_id, 
                        "tags": event.args.get("tags")
                    })

            elif event.operation == "DELETE":
                await cursor.execute(
                    "DELETE FROM clipboard WHERE id = %s AND user_id = %s",
                    (event.data_id, user_id)
                )
                await publish_event("data_deleted", {"data_id": event.data_id, "user_id": user_id})
            
            processed_count += 1

        await conn.commit()
        return SyncResponse(success=True, tag_mappings=[], processed_count=processed_count)

    except Exception as e:
        await conn.rollback()
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/items", response_model=ItemResponse)
async def create_item(
    item: ItemCreate, 
    user: Dict = Depends(get_current_user), 
    db=Depends(get_db)
):
    conn, cursor = db
    user_id = user["user_id"]
    try:
        # 공통 저장 함수 호출
        await _save_clipboard_item(cursor, item.model_dump(), user_id)
        
        await conn.commit()
        
        # 이벤트 발행 (태그 포함)
        payload = item.model_dump()
        payload["user_id"] = user_id
        await publish_event("clip_created", payload)

        return item

    except Exception as e:
        await conn.rollback()
        logger.error(f"Create item failed: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@app.post("/items/image")
async def upload_image(
    file: UploadFile = File(...),
    id: str = Form(...),
    format: str = Form(...),
    created_at: int = Form(...),
    user: Dict = Depends(get_current_user),
    db=Depends(get_db)
):
    conn, cursor = db
    user_id = user["user_id"]
    
    await cursor.execute("SELECT id FROM clipboard WHERE id = %s", (id,))
    if await cursor.fetchone():
         return JSONResponse(status_code=200, content={"id": id, "message": "Already exists"})

    try:
        contents = await file.read()
        file_size = len(contents)
        
        loop = asyncio.get_running_loop()
        try:
            image = await loop.run_in_executor(None, lambda: Image.open(io.BytesIO(contents)))
            width, height = image.size
        except Exception:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid image file")

        ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
        orig_name = f"{id}.{ext}"
        thumb_name = f"{id}_thumb.{ext}"
        
        orig_path_fs = os.path.join(original_dir, orig_name)
        thumb_path_fs = os.path.join(thumbnail_dir, thumb_name)
        
        orig_url = f"/local/original/{orig_name}"
        thumb_url = f"/local/thumbnail/{thumb_name}"

        async with aiofiles.open(orig_path_fs, 'wb') as f:
            await f.write(contents)

        def save_thumb():
            thumb = image.copy()
            thumb.thumbnail((256, 256))
            thumb.save(thumb_path_fs)
        await loop.run_in_executor(None, save_thumb)

        await cursor.execute(
            "INSERT INTO clipboard (id, user_id, content, type, format, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (id, user_id, orig_url, 'img', format, created_at)
        )
        await cursor.execute(
            "INSERT INTO image_meta (data_id, width, height, file_size, file_path, thumbnail_path) VALUES (%s, %s, %s, %s, %s, %s)",
            (id, width, height, file_size, orig_url, thumb_url)
        )
        await conn.commit()

        await publish_event("image_created", {
            "data_id": id, "user_id": user_id, "file_path": orig_path_fs, "created_at": created_at
        })

        return JSONResponse(status_code=201, content={"id": id, "message": "Uploaded"})

    except Exception as e:
        await conn.rollback()
        if 'orig_path_fs' in locals(): delete_local_file(orig_path_fs, original_dir)
        if 'thumb_path_fs' in locals(): delete_local_file(thumb_path_fs, thumbnail_dir)
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str, 
    user: Dict = Depends(get_current_user), 
    db=Depends(get_db)
):
    conn, cursor = db
    try:
        await cursor.execute("""
            SELECT c.user_id, im.file_path, im.thumbnail_path, c.type 
            FROM clipboard c
            LEFT JOIN image_meta im ON c.id = im.data_id
            WHERE c.id = %s
        """, (item_id,))
        
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        if row["user_id"] != user["user_id"]:
            raise HTTPException(403, "Permission denied")

        await cursor.execute("DELETE FROM clipboard WHERE id = %s", (item_id,))
        await conn.commit()

        await publish_event("data_deleted", {
            "data_id": item_id, "user_id": user["user_id"], "type": row["type"]
        })
        
        if row["file_path"]:
            delete_local_file(row["file_path"], original_dir)
        if row["thumbnail_path"]:
            delete_local_file(row["thumbnail_path"], thumbnail_dir)

    except HTTPException:
        await conn.rollback()
        raise
    except Exception as e:
        await conn.rollback()
        logger.error(f"Delete failed: {e}")
        raise HTTPException(500, "Internal Server Error")

@app.get("/clipboard-data", response_model=List[ClipboardDataResponse])
@app.get("/clipboard", response_model=List[ClipboardDataResponse])
async def get_user_clipboard_data(
    user: Dict = Depends(get_current_user), 
    db=Depends(get_db)
):
    conn, cursor = db
    try:
        await cursor.execute("""
            SELECT c.*, 
                   im.width, im.height, im.file_size,
                   im.file_path, im.thumbnail_path
            FROM clipboard c
            LEFT JOIN image_meta im ON c.id = im.data_id
            WHERE c.user_id = %s
            ORDER BY c.created_at DESC
        """, (user["user_id"],))
        
        results = await cursor.fetchall()
        data_list = []
        
        for row in results:
            img_meta = None
            if row.get("file_path"):
                img_meta = {k: row[k] for k in ["width", "height", "file_size", "file_path", "thumbnail_path"]}

            data_list.append({**row, "tags": [], "image_meta": img_meta})
            
        return data_list

    except Exception as e:
        logger.error(f"Fetch list failed: {e}")
        raise HTTPException(500, "Internal server error")

@app.post("/clipboard")
@app.post("/clipboard-data")
async def create_clipboard_data(
    id: str = Form(...),
    type: str = Form(...),
    format: str = Form(...),
    created_at: str = Form(...),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: Dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """클립보드 데이터 업로드"""
    conn, cursor = db
    try:
        # created_at ISO string을 Unix timestamp로 변환
        from datetime import datetime
        created_ts = int(datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp())
        
        # 기본 데이터 저장
        await cursor.execute("""
            INSERT INTO clipboard (id, user_id, type, format, content, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                content = VALUES(content),
                type = VALUES(type),
                format = VALUES(format)
        """, (id, user["user_id"], type, format, content or "", created_ts))
        
        # 이미지 파일 처리
        if type == "img" and file:
            # 이미지 저장 디렉토리
            upload_dir = "/app/uploads"
            os.makedirs(upload_dir, exist_ok=True)
            
            # 원본 파일 저장
            file_path = os.path.join(upload_dir, f"{id}.{format}")
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # 이미지 메타데이터 추출
            img = Image.open(io.BytesIO(content))
            width, height = img.size
            file_size = len(content)
            
            # 썸네일 생성
            thumb_path = os.path.join(upload_dir, f"{id}_thumb.jpg")
            img.thumbnail((200, 200))
            img.save(thumb_path, "JPEG", quality=85)
            
            # 메타데이터 저장
            await cursor.execute("""
                INSERT INTO image_meta (data_id, width, height, file_size, file_path, thumbnail_path)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    width = VALUES(width),
                    height = VALUES(height),
                    file_size = VALUES(file_size),
                    file_path = VALUES(file_path),
                    thumbnail_path = VALUES(thumbnail_path)
            """, (id, width, height, file_size, file_path, thumb_path))
        
        await conn.commit()
        
        # RabbitMQ 이벤트 발행 (선택사항)
        # await publish_event("clipboard.created", {...})
        
        return {"id": id, "status": "created"}
        
    except Exception as e:
        await conn.rollback()
        logger.error(f"Create clipboard data failed: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to create clipboard data: {str(e)}")

@app.get("/clipboard-data/{data_id}", response_model=ClipboardDataResponse)
async def get_single_clipboard_data(
    data_id: str, 
    user: Dict = Depends(get_current_user), 
    db=Depends(get_db)
):
    conn, cursor = db
    try:
        await cursor.execute("""
            SELECT c.*, 
                   im.width, im.height, im.file_size,
                   im.file_path, im.thumbnail_path
            FROM clipboard c
            LEFT JOIN image_meta im ON c.id = im.data_id
            WHERE c.id = %s AND c.user_id = %s
        """, (data_id, user["user_id"]))
        
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Data not found")

        img_meta = None
        if row.get("file_path"):
             img_meta = {k: row[k] for k in ["width", "height", "file_size", "file_path", "thumbnail_path"]}

        return {**row, "tags": [], "image_meta": img_meta}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fetch single failed: {e}")
        raise HTTPException(500, "Internal server error")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP error {exc.status_code} on {request.url}: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error on {request.url}: {exc.errors()}")
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})