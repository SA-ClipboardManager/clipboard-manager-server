"""
이미지 업로드 API 라우터
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.responses import JSONResponse

from ..services.image_service import ImageService
from ..services.clipboard_service import ClipboardService
from .dependencies import (
    get_image_service,
    get_clipboard_service,
    get_current_user,
    get_db
)
from ..core.logging import logger


router = APIRouter()


@router.post("/items/image")


@router.post("/clipboard")
@router.post("/clipboard-data")
async def create_clipboard_data(
    id: str = Form(...),
    type: str = Form(...),
    format: str = Form(...),
    created_at: str = Form(...),
    content: Optional[str] = Form(None),
    correlation_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user),
    clipboard_service: ClipboardService = Depends(get_clipboard_service),
    image_service: ImageService = Depends(get_image_service),
    db=Depends(get_db)
):
    """
    클립보드 데이터 생성 (텍스트 또는 이미지)
    """
    conn, cursor = db
    user_id = user["user_id"]
    
    try:
        await conn.begin()
        
        # 타임스탬프 변환
        from datetime import datetime
        created_ts = int(
            datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
        )
        
        # 기본 클립보드 아이템 생성
        from ..domain.models import ClipboardItemCreate
        from ..shared.utility.correlationId import generate_correlation_id
        
        item = ClipboardItemCreate(
            id=id,
            type=type,
            format=format,
            content=content or "",
            created_at=created_ts,
            correlation_id=correlation_id or generate_correlation_id()
        )
        
        await clipboard_service.create_item(item, user_id)
        
        # 이미지 파일 처리
        if type == "img" and file:
            file_content = await file.read()
            await image_service.upload_clipboard_image(
                file_content=file_content,
                item_id=id,
                format=format,
                created_at=created_ts,
                user_id=user_id,
                correlation_id=item.correlation_id
            )
        
        await conn.commit()
        return {"id": id, "status": "created"}
    
    except Exception as e:
        await conn.rollback()
        corr_id = correlation_id or id
        logger.error(f"Create clipboard data failed: {e} [correlation_id: {corr_id}]", exc_info=True)
        
        # 모니터링 에러 로그 발행
        from ..main import monitoring_publisher
        await monitoring_publisher.publish_error_log(
            correlation_id=corr_id,
            message=f"Create clipboard data failed for user {user_id}",
            exception=e
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create clipboard data: {str(e)}"
        )
