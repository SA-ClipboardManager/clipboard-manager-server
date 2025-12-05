"""
클립보드 서비스 (비즈니스 로직)
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..domain.models import (
    ClipboardItem, ClipboardItemCreate, ClipboardItemResponse,
    SyncEventItem, SyncResponse
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
        
        # 타입별 이벤트 발행
        if item_create.type == "txt":
            payload = item_create.model_dump()
            payload["user_id"] = user_id
            await self.message_broker.publish_event("crud.item.saved.txt", payload)
        elif item_create.type == "img":
            # 이미지 메타데이터 조회
            img_meta = await self.image_repo.get_by_data_id(item_create.id)
            
            payload = {
                "data_id": item_create.id,
                "user_id": user_id,
                "format": item_create.format,
                "created_at": item_create.created_at,
            }
            
            # 이미지 메타 정보가 있으면 URL 변환해서 포함
            if img_meta:
                payload["file_path"] = self._convert_path_to_url(img_meta.get("file_path"))
                payload["thumbnail_path"] = self._convert_path_to_url(img_meta.get("thumbnail_path"))
                payload["width"] = img_meta.get("width")
                payload["height"] = img_meta.get("height")
                payload["file_size"] = img_meta.get("file_size")
            
            await self.message_broker.publish_event("crud.item.saved.img", payload)
        
        return item_create
    
    async def sync_events(
        self,
        events: List[SyncEventItem],
        user_id: str
    ) -> SyncResponse:
        """동기화 이벤트 처리"""
        processed_count = 0
        
        for event in events:
            if event.operation in ["INSERT", "UPDATE"]:
                # 아이템 저장
                await self._save_item_from_sync(event.args, user_id)
                
                # 타입별 저장 성공 이벤트 발행
                if event.args.get("type") == "txt":
                    event_payload = {
                        "data_id": event.args.get("id"),
                        "user_id": user_id,
                        "content": event.args.get("content"),
                        "format": event.args.get("format"),
                        "created_at": event.args.get("created_at"),
                        "correlation_id": event.correlation_id
                    }
                    await self.message_broker.publish_event("crud.item.saved.txt", event_payload)
                    
                elif event.args.get("type") == "img":
                    # 이미지 메타데이터 조회
                    img_meta = await self.image_repo.get_by_data_id(event.args.get("id"))
                    
                    event_payload = {
                        "data_id": event.args.get("id"),
                        "user_id": user_id,
                        "format": event.args.get("format"),
                        "created_at": event.args.get("created_at"),
                        "correlation_id": event.correlation_id
                    }
                    
                    # 이미지 메타 정보가 있으면 URL 변환해서 포함
                    if img_meta:
                        event_payload["file_path"] = self._convert_path_to_url(img_meta.get("file_path"))
                        event_payload["thumbnail_path"] = self._convert_path_to_url(img_meta.get("thumbnail_path"))
                        event_payload["width"] = img_meta.get("width")
                        event_payload["height"] = img_meta.get("height")
                        event_payload["file_size"] = img_meta.get("file_size")
                    
                    await self.message_broker.publish_event("crud.item.saved.img", event_payload)
                
                # 태그 이벤트 발행
                if "tags" in event.args and event.args["tags"]:
                    await self.message_broker.publish_event("crud.item.tags.synced", {
                        "data_id": event.args.get("id"),
                        "user_id": user_id,
                        "tags": event.args.get("tags"),
                        "correlation_id": event.correlation_id
                    })
            
            elif event.operation == "DELETE":
                await self.clipboard_repo.delete(event.data_id, user_id)
                await self.message_broker.publish_event("crud.item.deleted", {
                    "data_id": event.data_id,
                    "user_id": user_id,
                    "correlation_id": event.correlation_id
                })
            
            processed_count += 1
        
        return SyncResponse(
            success=True,
            processed_count=processed_count,
            tag_mappings=[]
        )
    
    async def delete_item(self, item_id: str, user_id: str) -> Dict[str, Any]:
        """클립보드 아이템 삭제"""
        # 소유권 및 메타데이터 확인
        item = await self.clipboard_repo.get_with_ownership(item_id)
        
        if not item:
            return {"found": False}
        
        if item["user_id"] != user_id:
            return {"found": True, "authorized": False}
        
        # 삭제
        await self.clipboard_repo.delete(item_id, user_id)
        
        # 이벤트 발행
        await self.message_broker.publish_event("crud.item.deleted", {
            "data_id": item_id,
            "user_id": user_id,
            "type": item["type"]
        })
        
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
    
    async def _save_item_from_sync(self, item_data: dict, user_id: str):
        """동기화 데이터로부터 아이템 저장"""
        required_fields = ('id', 'type', 'format', 'created_at')
        if not all(k in item_data for k in required_fields):
            logger.warning(f"Missing required fields: {item_data.keys()}")
            return
        
        item = ClipboardItem(
            id=item_data['id'],
            user_id=user_id,
            type=item_data['type'],
            format=item_data['format'],
            content=item_data.get('content'),
            created_at=item_data['created_at']
        )
        
        await self.clipboard_repo.update(item)
    
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
