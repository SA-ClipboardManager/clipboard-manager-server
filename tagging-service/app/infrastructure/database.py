"""
MySQL database connection and session management
"""
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Text

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# SQLAlchemy Base
Base = declarative_base()


class TagModel(Base):
    """태그 테이블 모델"""
    __tablename__ = "tag"
    
    tag_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    source = Column(String(10), nullable=False)  # 'auto' or 'user'


class DataTagModel(Base):
    """데이터-태그 연결 테이블 모델"""
    __tablename__ = "data_tag"
    
    data_id = Column(String(255), primary_key=True)
    tag_id = Column(String(255), primary_key=True)


# 데이터베이스 엔진 및 세션
engine = None
async_session_maker = None


async def init_db(retries: int = 15, delay: int = 2):
    """데이터베이스 초기화"""
    global engine, async_session_maker
    
    for i in range(retries):
        try:
            engine = create_async_engine(
                settings.mysql_url,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
            
            # 테이블 생성
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            async_session_maker = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            logger.info(f"Database connected successfully (Attempt {i+1})")
            return
            
        except Exception as e:
            logger.warning(
                f"Database not ready (Attempt {i+1}/{retries}). "
                f"Retrying in {delay}s... Error: {e}"
            )
            if i == retries - 1:
                logger.error("Could not connect to database after multiple retries")
                raise e
            await asyncio.sleep(delay)


async def close_db():
    """데이터베이스 연결 종료"""
    global engine
    if engine:
        await engine.dispose()
        logger.info("Database connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """데이터베이스 세션 가져오기"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
