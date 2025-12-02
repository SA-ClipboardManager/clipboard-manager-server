"""
Redis 클라이언트 관리
"""
from redis.asyncio import Redis
from fastapi_limiter import FastAPILimiter

from ..core.config import settings
from ..core.logging import logger


class RedisManager:
    """Redis 연결 관리자"""
    
    def __init__(self):
        self.client: Optional[Redis] = None
    
    async def connect(self) -> Redis:
        """Redis 연결"""
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)
        await FastAPILimiter.init(self.client)
        logger.info("Redis connected successfully")
        return self.client
    
    async def disconnect(self):
        """Redis 연결 종료"""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")


# 싱글톤 인스턴스
redis_manager = RedisManager()
