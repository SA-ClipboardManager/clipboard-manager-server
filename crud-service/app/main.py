"""
메인 애플리케이션 엔트리포인트
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import settings
from .core.logging import logger
from .infrastructure.database import db_manager
from .infrastructure.message_broker import message_broker
from .infrastructure.redis_client import redis_manager
from .infrastructure.monitoring_provider import monitoring_publisher
from .api.clipboard_routes import router as clipboard_router
from .api.image_routes import router as image_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    try:
        # 인프라 초기화
        logger.info("Starting CRUD Service...")
        
        # 데이터베이스 연결
        await db_manager.connect()
        await db_manager.initialize_schema()
        
        # Redis 연결
        await redis_manager.connect()
        
        # RabbitMQ 연결
        await message_broker.connect()
        
        # 이미지 디렉토리 생성
        os.makedirs(settings.original_dir, exist_ok=True)
        os.makedirs(settings.thumbnail_dir, exist_ok=True)
        
        logger.info("CRUD Service started successfully")
        yield
    
    except Exception as e:
        logger.critical(f"Startup failed: {e}", exc_info=True)
        raise
    
    finally:
        # 리소스 정리
        logger.info("Shutting down CRUD Service...")
        await db_manager.disconnect()
        await redis_manager.disconnect()
        await message_broker.disconnect()
        logger.info("CRUD Service shut down complete")


# FastAPI 앱 생성
app = FastAPI(
    title="Clipboard CRUD Service",
    description="클립보드 데이터 관리 서비스",
    version="2.0.0",
    lifespan=lifespan
)

# 이미지 디렉토리 자동 생성
os.makedirs(settings.original_dir, exist_ok=True)
os.makedirs(settings.thumbnail_dir, exist_ok=True)

# 정적 파일 서빙
app.mount(
    "/local/original",
    StaticFiles(directory=settings.original_dir),
    name="original-images"
)
app.mount(
    "/local/thumbnail",
    StaticFiles(directory=settings.thumbnail_dir),
    name="thumbnail-images"
)

# 라우터 등록
app.include_router(clipboard_router, tags=["Clipboard"])
app.include_router(image_router, tags=["Images"])


# ----------------------------------------------------------------------
# 예외 핸들러
# ----------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 예외 핸들러"""
    logger.error(f"HTTP error {exc.status_code} on {request.url}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 검증 예외 핸들러"""
    logger.error(f"Validation error on {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """일반 예외 핸들러"""
    logger.error(f"Unexpected error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ----------------------------------------------------------------------
# 헬스체크 엔드포인트
# ----------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """헬스체크"""
    return {
        "status": "healthy",
        "service": "crud-service",
        "version": "2.0.0"
    }


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Clipboard CRUD Service",
        "version": "2.0.0",
        "status": "running"
    }
