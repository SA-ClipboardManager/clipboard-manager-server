"""
Repository implementations
"""
import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.domain.models import Tag, DataTag
from app.domain.repositories import ITagRepository, IDataTagRepository
from app.infrastructure.database import TagModel, DataTagModel
from app.core.logging import get_logger

logger = get_logger(__name__)


class TagRepository(ITagRepository):
    """태그 저장소 구현"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, tag: Tag) -> None:
        """태그 생성"""
        try:
            db_tag = TagModel(
                tag_id=tag.tag_id,
                name=tag.name,
                source=tag.source
            )
            self.session.add(db_tag)
            await self.session.commit()
            logger.info(f"Tag created: {tag.name} ({tag.source})")
        except IntegrityError:
            await self.session.rollback()
            logger.warning(f"Tag already exists: {tag.name} ({tag.source})")
    
    async def get_by_name_and_source(self, name: str, source: str) -> Optional[Tag]:
        """이름과 소스로 태그 조회"""
        stmt = select(TagModel).where(
            TagModel.name == name,
            TagModel.source == source
        )
        result = await self.session.execute(stmt)
        db_tag = result.scalar_one_or_none()
        
        if db_tag:
            return Tag(
                tag_id=db_tag.tag_id,
                name=db_tag.name,
                source=db_tag.source
            )
        return None
    
    async def get_or_create(self, name: str, source: str) -> Tag:
        """태그 조회 또는 생성"""
        # 먼저 조회
        existing = await self.get_by_name_and_source(name, source)
        if existing:
            return existing
        
        # 없으면 생성
        tag = Tag(
            tag_id=str(uuid.uuid4()),
            name=name,
            source=source
        )
        await self.create(tag)
        return tag


class DataTagRepository(IDataTagRepository):
    """데이터-태그 연결 저장소 구현"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, data_tag: DataTag) -> None:
        """데이터-태그 연결 생성"""
        try:
            db_data_tag = DataTagModel(
                data_id=data_tag.data_id,
                tag_id=data_tag.tag_id
            )
            self.session.add(db_data_tag)
            await self.session.commit()
            logger.info(f"DataTag created: {data_tag.data_id} -> {data_tag.tag_id}")
        except IntegrityError:
            await self.session.rollback()
            logger.warning(f"DataTag already exists: {data_tag.data_id} -> {data_tag.tag_id}")
    
    async def get_by_data_id(self, data_id: str) -> List[DataTag]:
        """데이터 ID로 연결 조회"""
        stmt = select(DataTagModel).where(DataTagModel.data_id == data_id)
        result = await self.session.execute(stmt)
        db_data_tags = result.scalars().all()
        
        return [
            DataTag(data_id=dt.data_id, tag_id=dt.tag_id)
            for dt in db_data_tags
        ]
    
    async def delete_by_data_id(self, data_id: str) -> None:
        """데이터 ID로 연결 삭제"""
        stmt = select(DataTagModel).where(DataTagModel.data_id == data_id)
        result = await self.session.execute(stmt)
        data_tags = result.scalars().all()
        
        for dt in data_tags:
            await self.session.delete(dt)
        
        await self.session.commit()
        logger.info(f"DataTags deleted for data_id: {data_id}")
    
    async def exists(self, data_id: str, tag_id: str) -> bool:
        """연결 존재 여부 확인"""
        stmt = select(DataTagModel).where(
            DataTagModel.data_id == data_id,
            DataTagModel.tag_id == tag_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
