import asyncio
import io
import json
import logging
import os
from contextlib import asynccontextmanager
# [FIX] Any가 추가되었습니다.
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

from pydantic import BaseModel, ConfigDict
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
    rabbitmq_host: str = "rabbitmq-broker"
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

settings = Settings()

# --------------------------------------------------------------------------
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

# RabbitMQ Stub
async def publish_event(topic: str, data: Dict):
    logger.info(f"[Event] Topic: {topic}, Data: {json.dumps(data)[:100]}...")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app_state.db_pool = await aiomysql.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            db=settings.db_name,
            autocommit=True, 
        )
        app_state.redis = Redis.from_url(settings.redis_url)
        await FastAPILimiter.init(app_state.redis)
        await initialize_database()
        
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