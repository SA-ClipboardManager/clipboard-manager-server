"""
Repository interfaces for tagging service
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from .models import Tag, DataTag


class ITagRepository(ABC):
    """태그 저장소 인터페이스"""
    
    @abstractmethod
    async def create(self, tag: Tag) -> None:
        """태그 생성"""
        pass
    
    @abstractmethod
    async def get_by_name_and_source(self, name: str, source: str) -> Optional[Tag]:
        """이름과 소스로 태그 조회"""
        pass
    
    @abstractmethod
    async def get_or_create(self, name: str, source: str) -> Tag:
        """태그 조회 또는 생성"""
        pass


class IDataTagRepository(ABC):
    """데이터-태그 연결 저장소 인터페이스"""
    
    @abstractmethod
    async def create(self, data_tag: DataTag) -> None:
        """데이터-태그 연결 생성"""
        pass
    
    @abstractmethod
    async def get_by_data_id(self, data_id: str) -> List[DataTag]:
        """데이터 ID로 연결 조회"""
        pass
    
    @abstractmethod
    async def delete_by_data_id(self, data_id: str) -> None:
        """데이터 ID로 연결 삭제"""
        pass
    
    @abstractmethod
    async def exists(self, data_id: str, tag_id: str) -> bool:
        """연결 존재 여부 확인"""
        pass


class IMessageConsumer(ABC):
    """메시지 컨슈머 인터페이스"""
    
    @abstractmethod
    async def start(self) -> None:
        """컨슈머 시작"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """컨슈머 중지"""
        pass
