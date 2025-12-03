"""
RabbitMQ message consumer implementation
embedding-service의 message_consumer.py 참조
"""
import json
import asyncio
from typing import Callable, Optional, Awaitable
from aio_pika import connect, IncomingMessage, Connection, Channel, Queue

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.repositories import IMessageConsumer
from app.domain.models import TaggingTask

logger = get_logger(__name__)


class RabbitMQConsumer(IMessageConsumer):
    """RabbitMQ 메시지 컨슈머"""
    
    def __init__(self, message_handler: Callable[[TaggingTask], Awaitable[None]]):
        """
        RabbitMQ 컨슈머 초기화
        
        Args:
            message_handler: 메시지를 처리할 비동기 함수
        """
        self.rabbitmq_url = settings.rabbitmq_url
        self.queue_name = settings.RABBITMQ_QUEUE
        self.queue_durable = settings.RABBITMQ_QUEUE_DURABLE
        self.exchange_name = settings.RABBITMQ_EXCHANGE
        self.routing_key = settings.RABBITMQ_ROUTING_KEY
        self.message_handler = message_handler
        
        self._connection: Optional[Connection] = None
        self._channel: Optional[Channel] = None
        self._queue: Optional[Queue] = None
        
        logger.info(f"Initialized RabbitMQ consumer for queue: {self.queue_name}")
        logger.info(f"Subscribing to exchange: {self.exchange_name}, routing_key: {self.routing_key}")
    
    async def start(self):
        """메시지 컨슘 시작"""
        try:
            # RabbitMQ 연결
            logger.info(f"Connecting to RabbitMQ: {self.rabbitmq_url}")
            self._connection = await connect(self.rabbitmq_url)
            self._channel = await self._connection.channel()
            
            # Exchange 선언 (topic 타입)
            exchange = await self._channel.declare_exchange(
                self.exchange_name,
                "topic",
                durable=True
            )
            
            # Queue 선언
            self._queue = await self._channel.declare_queue(
                self.queue_name,
                durable=self.queue_durable
            )
            
            # Queue를 Exchange에 바인딩
            await self._queue.bind(
                exchange=self.exchange_name,
                routing_key=self.routing_key
            )
            
            logger.info(f"Connected to queue: {self.queue_name}")
            logger.info(f"Bound to exchange: {self.exchange_name} with routing_key: {self.routing_key}")
            logger.info("Waiting for messages. To exit press CTRL+C")
            
            # 메시지 컨슘 시작
            await self._queue.consume(self._on_message)
            
        except Exception as e:
            logger.error(f"Failed to start consumer: {e}")
            raise
    
    async def stop(self):
        """메시지 컨슘 중지"""
        try:
            logger.info("Stopping message consumer...")
            
            if self._channel:
                await self._channel.close()
            
            if self._connection:
                await self._connection.close()
            
            logger.info("Message consumer stopped")
            
        except Exception as e:
            logger.error(f"Error stopping consumer: {e}")
    
    async def _on_message(self, message: IncomingMessage):
        """
        메시지 수신 핸들러
        
        Args:
            message: 수신된 메시지
        """
        async with message.process():
            try:
                # 메시지 파싱
                body = json.loads(message.body.decode())
                logger.info(f"Received message: {body.get('event')}")
                logger.info(f"Message body: {body}")
                
                # crud-service가 { event, data: {...} } 형태로 보낼 수도 있음
                payload = body.get("data") or body
                
                # TaggingTask 생성 (payload에서 직접 추출)
                task = TaggingTask(
                    data_id=payload.get("data_id"),
                    user_id=payload.get("user_id") or body.get("user_id"),
                    file_path=payload.get("file_path"),
                    thumbnail_path=payload.get("thumbnail_path"),
                    created_at=payload.get("created_at"),
                    format=payload.get("format"),
                    width=payload.get("width"),
                    height=payload.get("height"),
                    file_size=payload.get("file_size")
                )
                
                # 메시지 처리
                await self.message_handler(task)
                logger.info(f"Successfully processed message for data_id: {task.data_id}")
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode message: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
