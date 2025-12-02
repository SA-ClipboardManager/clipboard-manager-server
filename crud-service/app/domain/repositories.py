"""
리포지토리 인터페이스 정의 (추상화)
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from .models import ClipboardItem, ImageMeta


class IClipboardRepository(ABC):
    """클립보드 리포지토리 인터페이스"""
    
    @abstractmethod
    async def create(self, item: ClipboardItem) -> None:
        """클립보드 아이템 생성"""
        pass
    
    @abstractmethod
    async def update(self, item: ClipboardItem) -> None:
        """클립보드 아이템 업데이트"""
        pass
    
    @abstractmethod
    async def delete(self, item_id: str, user_id: str) -> None:
        """클립보드 아이템 삭제"""
        pass
    
    @abstractmethod
    async def get_by_id(self, item_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """ID로 클립보드 아이템 조회"""
        pass
    
    @abstractmethod
    async def get_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 모든 클립보드 아이템 조회"""
        pass
    
    @abstractmethod
    async def exists(self, item_id: str) -> bool:
        """아이템 존재 여부 확인"""
        pass


class IImageMetaRepository(ABC):
    """이미지 메타데이터 리포지토리 인터페이스"""
    
    @abstractmethod
    async def create(self, meta: ImageMeta) -> None:
        """이미지 메타데이터 생성"""
        pass
    
    @abstractmethod
    async def update(self, meta: ImageMeta) -> None:
        """이미지 메타데이터 업데이트"""
        pass
    
    @abstractmethod
    async def get_by_data_id(self, data_id: str) -> Optional[ImageMeta]:
        """데이터 ID로 이미지 메타데이터 조회"""
        pass
