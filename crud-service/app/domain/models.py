"""
도메인 모델 정의
"""
from typing import Optional, List, Literal, Any, Dict
from pydantic import BaseModel, Field


class ClipboardItem(BaseModel):
    """클립보드 아이템 도메인 모델"""
    id: str
    user_id: str
    type: Literal["txt", "img"]
    format: str
    content: Optional[str] = None
    created_at: int


class ImageMeta(BaseModel):
    """이미지 메타데이터 도메인 모델"""
    data_id: str
    width: int
    height: int
    file_size: int
    file_path: str
    thumbnail_path: Optional[str] = None


class ClipboardItemCreate(BaseModel):
    """클립보드 아이템 생성 요청"""
    id: str
    content: Optional[str] = None
    type: Literal["txt", "img"]
    format: str
    created_at: int
    tags: Optional[List[Any]] = []
    correlation_id: Optional[str] = None  # 요청 추적용 ID


class ClipboardItemResponse(BaseModel):
    """클립보드 아이템 응답"""
    id: str
    user_id: str
    type: str
    format: str
    content: str
    created_at: int
    image_meta: Optional["ImageMetaResponse"] = None
    tags: List[Any] = []


class ImageMetaResponse(BaseModel):
    """이미지 메타데이터 응답"""
    width: int
    height: int
    file_size: int
    file_path: str
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None  # 클라이언트 호환성


class SyncEventItem(BaseModel):
    """동기화 이벤트 아이템"""
    operation: Literal["INSERT", "UPDATE", "DELETE"]
    data_id: str
    args: Dict[str, Any]
    correlation_id: str
    local_outbox_id: int


class SyncResponse(BaseModel):
    """동기화 응답"""
    success: bool
    processed_count: int
    tag_mappings: List[Dict[str, str]] = []
