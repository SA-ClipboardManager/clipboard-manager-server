"""
리포지토리 구현체
"""
from typing import Optional, List, Dict, Any
import aiomysql

from ..domain.models import ClipboardItem, ImageMeta
from ..domain.repositories import IClipboardRepository, IImageMetaRepository
from ..core.logging import logger


class ClipboardRepository(IClipboardRepository):
    """클립보드 리포지토리 MySQL 구현체"""
    
    def __init__(self, conn: aiomysql.Connection, cursor: aiomysql.Cursor):
        self.conn = conn
        self.cursor = cursor
    
    async def create(self, item: ClipboardItem) -> None:
        """클립보드 아이템 생성"""
        await self.cursor.execute(
            """
            INSERT INTO clipboard (id, user_id, content, type, format, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (item.id, item.user_id, item.content, item.type, item.format, item.created_at)
        )
    
    async def update(self, item: ClipboardItem) -> None:
        """클립보드 아이템 업데이트"""
        await self.cursor.execute(
            """
            INSERT INTO clipboard (id, user_id, content, type, format, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                content = VALUES(content), 
                created_at = VALUES(created_at)
            """,
            (item.id, item.user_id, item.content, item.type, item.format, item.created_at)
        )
    
    async def delete(self, item_id: str, user_id: str) -> None:
        """클립보드 아이템 삭제"""
        await self.cursor.execute(
            "DELETE FROM clipboard WHERE id = %s AND user_id = %s",
            (item_id, user_id)
        )
    
    async def get_by_id(self, item_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """ID로 클립보드 아이템 조회"""
        await self.cursor.execute(
            """
            SELECT c.*, 
                   im.width, im.height, im.file_size,
                   im.file_path, im.thumbnail_path
            FROM clipboard c
            LEFT JOIN image_meta im ON c.id = im.data_id
            WHERE c.id = %s AND c.user_id = %s
            """,
            (item_id, user_id)
        )
        return await self.cursor.fetchone()
    
    async def get_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 모든 클립보드 아이템 조회"""
        await self.cursor.execute(
            """
            SELECT c.*, 
                   im.width, im.height, im.file_size,
                   im.file_path, im.thumbnail_path
            FROM clipboard c
            LEFT JOIN image_meta im ON c.id = im.data_id
            WHERE c.user_id = %s
            ORDER BY c.created_at DESC
            """,
            (user_id,)
        )
        return await self.cursor.fetchall()
    
    async def exists(self, item_id: str) -> bool:
        """아이템 존재 여부 확인"""
        await self.cursor.execute(
            "SELECT id FROM clipboard WHERE id = %s",
            (item_id,)
        )
        result = await self.cursor.fetchone()
        return result is not None
    
    async def get_with_ownership(self, item_id: str) -> Optional[Dict[str, Any]]:
        """아이템 조회 (소유권 정보 포함)"""
        await self.cursor.execute(
            """
            SELECT c.user_id, im.file_path, im.thumbnail_path, c.type 
            FROM clipboard c
            LEFT JOIN image_meta im ON c.id = im.data_id
            WHERE c.id = %s
            """,
            (item_id,)
        )
        return await self.cursor.fetchone()


class ImageMetaRepository(IImageMetaRepository):
    """이미지 메타데이터 리포지토리 MySQL 구현체"""
    
    def __init__(self, conn: aiomysql.Connection, cursor: aiomysql.Cursor):
        self.conn = conn
        self.cursor = cursor
    
    async def create(self, meta: ImageMeta) -> None:
        """이미지 메타데이터 생성"""
        await self.cursor.execute(
            """
            INSERT INTO image_meta (data_id, width, height, file_size, file_path, thumbnail_path)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (meta.data_id, meta.width, meta.height, meta.file_size, 
             meta.file_path, meta.thumbnail_path)
        )
    
    async def update(self, meta: ImageMeta) -> None:
        """이미지 메타데이터 업데이트"""
        await self.cursor.execute(
            """
            INSERT INTO image_meta (data_id, width, height, file_size, file_path, thumbnail_path)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                width = VALUES(width),
                height = VALUES(height),
                file_size = VALUES(file_size),
                file_path = VALUES(file_path),
                thumbnail_path = VALUES(thumbnail_path)
            """,
            (meta.data_id, meta.width, meta.height, meta.file_size, 
             meta.file_path, meta.thumbnail_path)
        )
    
    async def get_by_data_id(self, data_id: str) -> Optional[ImageMeta]:
        """데이터 ID로 이미지 메타데이터 조회"""
        await self.cursor.execute(
            """
            SELECT data_id, width, height, file_size, file_path, thumbnail_path
            FROM image_meta
            WHERE data_id = %s
            """,
            (data_id,)
        )
        row = await self.cursor.fetchone()
        if row:
            return ImageMeta(**row)
        return None
