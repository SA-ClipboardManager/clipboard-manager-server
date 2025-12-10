"""
의존성 주입 설정
"""
from typing import AsyncGenerator, Tuple
from fastapi import Depends, Request
import aiomysql

from ..infrastructure.database import db_manager
from ..infrastructure.repositories import ClipboardRepository, ImageMetaRepository
from ..infrastructure.message_broker import message_broker
from ..infrastructure.image_processor import ImageProcessor
from ..services.clipboard_service import ClipboardService
from ..services.image_service import ImageService
from ..core.logging import logger
from ..main import monitoring_publisher


# ----------------------------------------------------------------------
# Database Dependencies
# ----------------------------------------------------------------------

async def get_db() -> AsyncGenerator[Tuple[aiomysql.Connection, aiomysql.Cursor], None]:
    """데이터베이스 커넥션 의존성"""
    async for conn_cursor in db_manager.get_connection():
        yield conn_cursor


# ----------------------------------------------------------------------
# Repository Dependencies
# ----------------------------------------------------------------------

async def get_clipboard_repository(
    db: Tuple[aiomysql.Connection, aiomysql.Cursor] = Depends(get_db)
) -> ClipboardRepository:
    """클립보드 리포지토리 의존성"""
    conn, cursor = db
    return ClipboardRepository(conn, cursor)


async def get_image_repository(
    db: Tuple[aiomysql.Connection, aiomysql.Cursor] = Depends(get_db)
) -> ImageMetaRepository:
    """이미지 메타 리포지토리 의존성"""
    conn, cursor = db
    return ImageMetaRepository(conn, cursor)


# ----------------------------------------------------------------------
# Infrastructure Dependencies
# ----------------------------------------------------------------------

def get_image_processor() -> ImageProcessor:
    """이미지 프로세서 의존성 (싱글톤)"""
    return ImageProcessor()


# ----------------------------------------------------------------------
# Service Dependencies
# ----------------------------------------------------------------------

async def get_clipboard_service(
    clipboard_repo: ClipboardRepository = Depends(get_clipboard_repository),
    image_repo: ImageMetaRepository = Depends(get_image_repository)
) -> ClipboardService:
    """클립보드 서비스 의존성"""
    return ClipboardService(clipboard_repo, image_repo, message_broker, monitoring_publisher)


async def get_image_service(
    clipboard_repo: ClipboardRepository = Depends(get_clipboard_repository),
    image_repo: ImageMetaRepository = Depends(get_image_repository),
    image_processor: ImageProcessor = Depends(get_image_processor)
) -> ImageService:
    """이미지 서비스 의존성"""
    return ImageService(clipboard_repo, image_repo, message_broker, image_processor, monitoring_publisher)


# ----------------------------------------------------------------------
# Auth Dependencies
# ----------------------------------------------------------------------

async def get_current_user(request: Request) -> dict:
    """현재 사용자 정보 추출 (Gateway Offloading)"""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        logger.warning("Direct access without Gateway Header")
        return {"user_id": "test-user"}
    return {"user_id": user_id}
