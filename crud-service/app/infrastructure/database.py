"""
데이터베이스 연결 및 초기화
"""
import asyncio
from typing import AsyncGenerator
import aiomysql
from aiomysql import Pool

from ..core.config import settings
from ..core.logging import logger


# 데이터베이스 스키마
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS clipboard (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    type ENUM('img', 'txt') NOT NULL,
    format VARCHAR(50) NOT NULL,
    content LONGTEXT,
    created_at BIGINT NOT NULL,
    INDEX idx_user_created (user_id, created_at)
);

CREATE TABLE IF NOT EXISTS image_meta (
    data_id VARCHAR(36) PRIMARY KEY,
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    file_path TEXT NOT NULL,
    thumbnail_path TEXT,
    FOREIGN KEY (data_id) REFERENCES clipboard(id) ON DELETE CASCADE
);
"""


class DatabaseManager:
    """데이터베이스 연결 관리자"""
    
    def __init__(self):
        self.pool: Optional[Pool] = None
    
    async def connect(self, retries: int = 15, delay: int = 2) -> Pool:
        """데이터베이스 연결 (재시도 로직 포함)"""
        for i in range(retries):
            try:
                logger.info(f"Attempting to connect to DB host: {settings.db_host}")
                self.pool = await aiomysql.create_pool(
                    host=settings.db_host,
                    port=settings.db_port,
                    user=settings.db_user,
                    password=settings.db_password,
                    db=settings.db_name,
                    autocommit=True,
                    minsize=5,
                    maxsize=20,
                )
                logger.info(f"Database connected successfully (Attempt {i+1})")
                return self.pool
            except Exception as e:
                logger.warning(
                    f"DB not ready (Attempt {i+1}/{retries}). "
                    f"Retrying in {delay}s... Error: {e}"
                )
                if i == retries - 1:
                    raise ConnectionError(
                        "Failed to connect to database after multiple retries"
                    )
                await asyncio.sleep(delay)
    
    async def disconnect(self):
        """데이터베이스 연결 종료"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Database connection closed")
    
    async def initialize_schema(self):
        """데이터베이스 스키마 초기화"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    for statement in CREATE_TABLES_SQL.strip().split(';'):
                        if statement.strip():
                            await cursor.execute(statement.strip() + ';')
                    await conn.commit()
                    logger.info("Database schema initialized")
                except Exception as e:
                    logger.error(f"Schema initialization failed: {e}")
                    raise
    
    async def get_connection(self) -> AsyncGenerator:
        """데이터베이스 커넥션 제공 (의존성 주입용)"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                yield conn, cursor


# 싱글톤 인스턴스
db_manager = DatabaseManager()
