"""
클립보드 서비스 (비즈니스 로직)
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..domain.models import (
    ClipboardItem, ClipboardItemCreate, ClipboardItemResponse
)
from ..domain.repositories import IClipboardRepository, IImageMetaRepository
from ..infrastructure.message_broker import MessageBroker
from ..core.logging import logger


class ClipboardService:
    """클립보드 비즈니스 로직 서비스"""
    
    def __init__(
        self,
        clipboard_repo: IClipboardRepository,
        image_repo: IImageMetaRepository,
        message_broker: MessageBroker
    ):
        self.clipboard_repo = clipboard_repo
        self.image_repo = image_repo
        self.message_broker = message_broker
    
    async def create_item(
        self,
        item_create: ClipboardItemCreate,
        user_id: str
    ) -> ClipboardItemCreate:
        """클립보드 아이템 생성"""
        # 도메인 모델로 변환
        item = ClipboardItem(
            id=item_create.id,
            user_id=user_id,
            type=item_create.type,
            format=item_create.format,
            content=item_create.content,
            created_at=item_create.created_at
        )
        
        # 저장
        await self.clipboard_repo.update(item)
        
        # correlation_id 설정 (없으면 data_id 사용 - 하위 호환성)
        correlation_id = item_create.correlation_id or item_create.id
        
        # 타입별 이벤트 발행
        if item_create.type == "txt":
            payload = item_create.model_dump()
            payload["user_id"] = user_id
            payload["correlation_id"] = correlation_id
            await self.message_broker.publish_event("service.crud.item.saved.txt", payload)
            logger.info(f"Published event: service.crud.item.saved.txt for item {item_create.id} [correlation_id: {correlation_id}]")
        # 이미지는 image_service.upload_clipboard_image에서 이미 이벤트 발행함 (중복 방지)
        
        return item_create
    
    async def delete_item(self, item_id: str, user_id: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """클립보드 아이템 삭제"""
        # 소유권 및 메타데이터 확인
        item = await self.clipboard_repo.get_with_ownership(item_id)
        
        if not item:
            return {"found": False}
        
        if item["user_id"] != user_id:
            return {"found": True, "authorized": False}
        
        # 삭제
        await self.clipboard_repo.delete(item_id, user_id)
        
        # correlation_id 설정 (없으면 item_id 사용 - 하위 호환성)
        corr_id = correlation_id or item_id
        
        # 이벤트 발행
        await self.message_broker.publish_event("service.crud.item.deleted", {
            "data_id": item_id,
            "user_id": user_id,
            "type": item["type"],
            "correlation_id": corr_id
        })
        logger.info(f"Published event: service.crud.item.deleted for item {item_id} [correlation_id: {corr_id}]")
        
        return {
            "found": True,
            "authorized": True,
            "file_path": item.get("file_path"),
            "thumbnail_path": item.get("thumbnail_path")
        }
    
    async def get_item(
        self,
        item_id: str,
        user_id: str
    ) -> Optional[ClipboardItemResponse]:
        """클립보드 아이템 조회"""
        row = await self.clipboard_repo.get_by_id(item_id, user_id)
        
        if not row:
            return None
        
        return self._row_to_response(row)
    
    async def get_user_items(self, user_id: str) -> List[ClipboardItemResponse]:
        """사용자의 모든 클립보드 아이템 조회"""
        rows = await self.clipboard_repo.get_by_user(user_id)
        return [self._row_to_response(row) for row in rows]
    
    def _convert_path_to_url(self, path: Optional[str]) -> Optional[str]:
        """파일 경로를 HTTP URL로 변환"""
        from ..core.config import settings
        import os
        
        if not path:
            return None
        
        # 이미 HTTP URL인 경우
        if path.startswith("http://") or path.startswith("https://"):
            return path
        
        # /app/shared_images/uploads/... 형식을 /local/... 형식으로 변환
        if path.startswith("/app/shared_images/uploads/"):
            rel_path = path.replace("/app/shared_images/uploads/", "")
            return f"{settings.server_url}/local/{rel_path}"
        elif path.startswith("/app/shared_images/"):
            # 레거시 경로 처리
            filename = os.path.basename(path)
            return f"{settings.server_url}/local/original/{filename}"
        elif path.startswith("/local/"):
            return f"{settings.server_url}{path}"
        
        return path
    
    def _convert_url_to_fs_path(self, url_path: Optional[str]) -> Optional[str]:
        """URL 경로를 파일시스템 경로로 변환 (임베딩 서비스용)"""
        from ..core.config import settings
        import os
        
        if not url_path:
            return None
        
        # /local/original/xxx.png -> /app/shared_images/uploads/original/xxx.png
        if url_path.startswith("/local/original/"):
            filename = url_path.replace("/local/original/", "")
            return os.path.join(settings.original_dir, filename)
        elif url_path.startswith("/local/thumbnail/"):
            filename = url_path.replace("/local/thumbnail/", "")
            return os.path.join(settings.thumbnail_dir, filename)
        
        # 이미 파일시스템 경로인 경우
        return url_path
    
    def _row_to_response(self, row: Dict[str, Any]) -> ClipboardItemResponse:
        """DB 행을 응답 모델로 변환"""
        from ..core.config import settings
        import os
        
        img_meta = None
        content = row.get("content", "")
        
        if row.get("file_path"):
            # 로컬 경로를 HTTP URL로 변환
            file_path = row["file_path"]
            thumbnail_path = row.get("thumbnail_path")
            
            print(f"[DEBUG] Original file_path: {file_path}")
            print(f"[DEBUG] Original thumbnail_path: {thumbnail_path}")
            
            # /app/shared_images/uploads/... 형식을 /local/... 형식으로 변환
            if file_path and file_path.startswith("/app/shared_images/uploads/"):
                # /app/shared_images/uploads/original/xxx.png -> /local/original/xxx.png
                rel_path = file_path.replace("/app/shared_images/uploads/", "")
                file_path = f"/local/{rel_path}"
                print(f"[DEBUG] Converted file_path: {file_path}")
            elif file_path and file_path.startswith("/app/shared_images/"):
                # 레거시: /app/shared_images/xxx.png -> /local/original/xxx.png
                filename = os.path.basename(file_path)
                file_path = f"/local/original/{filename}"
                print(f"[DEBUG] Legacy converted file_path: {file_path}")
            
            if thumbnail_path and thumbnail_path.startswith("/app/shared_images/uploads/"):
                rel_path = thumbnail_path.replace("/app/shared_images/uploads/", "")
                thumbnail_path = f"/local/{rel_path}"
                print(f"[DEBUG] Converted thumbnail_path: {thumbnail_path}")
            elif thumbnail_path and thumbnail_path.startswith("/app/shared_images/"):
                filename = os.path.basename(thumbnail_path)
                thumbnail_path = f"/local/thumbnail/{filename}"
                print(f"[DEBUG] Legacy converted thumbnail_path: {thumbnail_path}")
            
            # /local/... 형식이면 전체 URL로 변환
            if file_path and file_path.startswith("/local/"):
                file_path = f"{settings.server_url}{file_path}"
            if thumbnail_path and thumbnail_path.startswith("/local/"):
                thumbnail_path = f"{settings.server_url}{thumbnail_path}"
            
            # 이미지인 경우 content를 file_path로 설정 (UI에서 src로 사용)
            if row.get("type") == "img" and file_path:
                content = file_path
            
            img_meta = {
                "width": row.get("width"),
                "height": row.get("height"),
                "file_size": row.get("file_size"),
                "file_path": file_path,
                "thumbnail_path": thumbnail_path,
                "thumbnail_url": thumbnail_path  # 클라이언트 호환성
            }
        
        return ClipboardItemResponse(
            id=row["id"],
            user_id=row["user_id"],
            type=row["type"],
            format=row["format"],
            content=content,
            created_at=row["created_at"],
            image_meta=img_meta,
            tags=[]
        )
