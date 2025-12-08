"""
클립보드 API 라우터
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

from ..domain.models import (
    ClipboardItemCreate, ClipboardItemResponse,
    SyncEventItem, SyncResponse
)
from ..services.clipboard_service import ClipboardService
from ..services.image_service import ImageService
from .dependencies import get_clipboard_service, get_current_user, get_db
from ..core.logging import logger


router = APIRouter()


@router.post("/sync/events", response_model=SyncResponse)
async def handle_sync_events(
    events: List[SyncEventItem],
    user: dict = Depends(get_current_user),
    service: ClipboardService = Depends(get_clipboard_service),
    db=Depends(get_db)
):
    """
    클라이언트 Outbox 동기화 처리
    """
    conn, cursor = db
    user_id = user["user_id"]
    
    try:
        await conn.begin()
        result = await service.sync_events(events, user_id)
        await conn.commit()
        return result
    except Exception as e:
        await conn.rollback()
        correlation_id = events[0].correlation_id if events else "unknown"
        logger.error(f"Sync failed: {e} [correlation_id: {correlation_id}]", exc_info=True)
        
        # 모니터링 에러 로그 발행
        from ..main import monitoring_publisher
        await monitoring_publisher.publish_error_log(
            correlation_id=correlation_id,
            message=f"Sync failed for user {user_id}",
            exception=e
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/items", response_model=ClipboardItemCreate)
async def create_item(
    item: ClipboardItemCreate,
    user: dict = Depends(get_current_user),
    service: ClipboardService = Depends(get_clipboard_service),
    db=Depends(get_db)
):
    """
    클립보드 아이템 생성
    """
    conn, cursor = db
    user_id = user["user_id"]
    
    try:
        await conn.begin()
        result = await service.create_item(item, user_id)
        await conn.commit()
        return result
    except Exception as e:
        await conn.rollback()
        correlation_id = item.correlation_id or item.id
        logger.error(f"Create item failed: {e} [correlation_id: {correlation_id}]", exc_info=True)
        
        # 모니터링 에러 로그 발행
        from ..main import monitoring_publisher
        await monitoring_publisher.publish_error_log(
            correlation_id=correlation_id,
            message=f"Create item failed for user {user_id}",
            exception=e
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create item"
        )


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    user: dict = Depends(get_current_user),
    service: ClipboardService = Depends(get_clipboard_service),
    db=Depends(get_db)
):
    """
    클립보드 아이템 삭제
    """
    conn, cursor = db
    user_id = user["user_id"]
    
    try:
        await conn.begin()
        # correlation_id 생성 (요청 추적용)
        from ..shared.utility.correlationId import generate_correlation_id
        correlation_id = generate_correlation_id()
        result = await service.delete_item(item_id, user_id, correlation_id)
        await conn.commit()
        
        if not result["found"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found"
            )
        
        if not result["authorized"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        
        # 이미지 파일 삭제
        if result.get("file_path") or result.get("thumbnail_path"):
            ImageService.delete_image_files(
                result.get("file_path"),
                result.get("thumbnail_path")
            )
        
        return None
    
    except HTTPException:
        await conn.rollback()
        raise
    except Exception as e:
        await conn.rollback()
        logger.error(f"Delete failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/clipboard-data", response_model=List[ClipboardItemResponse])
@router.get("/clipboard", response_model=List[ClipboardItemResponse])
async def get_user_clipboard_data(
    user: dict = Depends(get_current_user),
    service: ClipboardService = Depends(get_clipboard_service)
):
    """
    사용자의 모든 클립보드 데이터 조회
    """
    try:
        return await service.get_user_items(user["user_id"])
    except Exception as e:
        logger.error(f"Fetch list failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/clipboard-data/{data_id}", response_model=ClipboardItemResponse)
async def get_single_clipboard_data(
    data_id: str,
    user: dict = Depends(get_current_user),
    service: ClipboardService = Depends(get_clipboard_service)
):
    """
    특정 클립보드 데이터 조회
    """
    try:
        result = await service.get_item(data_id, user["user_id"])
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data not found"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fetch single failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
