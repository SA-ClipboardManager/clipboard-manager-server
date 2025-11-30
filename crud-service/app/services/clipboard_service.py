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
        
        # 이벤트 발행
        payload = item_create.model_dump()
        payload["user_id"] = user_id
        await self.message_broker.publish_event("clip_created", payload)
        
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
                
                # 태그 이벤트 발행
                if "tags" in event.args and event.args["tags"]:
                    await self.message_broker.publish_event("clip_synced_tags", {
                        "data_id": event.args.get("id"),
                        "user_id": user_id,
                        "tags": event.args.get("tags"),
                        "correlation_id": event.correlation_id
                    })
            
            elif event.operation == "DELETE":
                await self.clipboard_repo.delete(event.data_id, user_id)
                await self.message_broker.publish_event("data_deleted", {
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
        await self.message_broker.publish_event("data_deleted", {
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
    
    def _row_to_response(self, row: Dict[str, Any]) -> ClipboardItemResponse:
        """DB 행을 응답 모델로 변환"""
        img_meta = None
        if row.get("file_path"):
            img_meta = {
                k: row[k]
                for k in ["width", "height", "file_size", "file_path", "thumbnail_path"]
                if k in row
            }
        
        return ClipboardItemResponse(
            id=row["id"],
            user_id=row["user_id"],
            type=row["type"],
            format=row["format"],
            content=row.get("content", ""),
            created_at=row["created_at"],
            image_meta=img_meta,
            tags=[]
        )
