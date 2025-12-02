"""
메시지 브로커 (RabbitMQ) 연결 및 관리
"""
import asyncio
import json
from typing import Dict, Any, Optional
import aio_pika
from aio_pika import Channel
from aio_pika.abc import AbstractRobustConnection

from ..core.config import settings
from ..core.logging import logger


class MessageBroker:
    """RabbitMQ 메시지 브로커 관리자"""
    
    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[Channel] = None
    
    async def connect(self, retries: int = 15, delay: int = 2) -> Channel:
        """RabbitMQ 연결 (재시도 로직 포함)"""
        for i in range(retries):
            try:
                self.connection = await aio_pika.connect_robust(
                    settings.rabbitmq_url,
                    reconnect_interval=5
                )
                self.channel = await self.connection.channel()
                logger.info(f"RabbitMQ connected successfully (Attempt {i+1})")
                return self.channel
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.warning(
                    f"RabbitMQ not ready (Attempt {i+1}/{retries}). "
                    f"Retrying in {delay}s..."
                )
                if i == retries - 1:
                    logger.error("Could not connect to RabbitMQ after multiple retries")
                    raise e
                await asyncio.sleep(delay)
    
    async def disconnect(self):
        """RabbitMQ 연결 종료"""
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        
        logger.info("RabbitMQ connection closed")
    
    async def publish_event(self, topic: str, data: Dict[str, Any]):
        """이벤트 발행"""
        if not self.channel:
            logger.error("RabbitMQ channel not available")
            return
        
        try:
            # 이벤트 타입에 따라 적절한 exchange 선택
            if topic.startswith("crud:"):
                # CRUD 이벤트는 topic exchange로 발행
                exchange = await self.channel.declare_exchange(
                    "crud_events",
                    aio_pika.ExchangeType.TOPIC,
                    durable=True
                )
                routing_key = topic
            else:
                # 기존 notifications는 fanout으로 유지
                exchange = await self.channel.declare_exchange(
                    "notifications",
                    aio_pika.ExchangeType.FANOUT
                )
                routing_key = ""
            
            # 메시지 생성
            message_body = {
                "event": topic,
                "data": data,
                "user_id": data.get("user_id")
            }
            
            message = aio_pika.Message(
                body=json.dumps(message_body).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            
            # 메시지 발행
            await exchange.publish(message, routing_key=routing_key)
            logger.info(f"[MQ Sent] Event: {topic}, User: {data.get('user_id')}, Data: {data.get('data_id')}")
        
        except Exception as e:
            logger.error(f"Failed to publish event: {e}", exc_info=True)


# 싱글톤 인스턴스
message_broker = MessageBroker()
