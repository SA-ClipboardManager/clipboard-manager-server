"""
RabbitMQ message consumer implementation.
Consumes image embedding tasks from the message queue.
"""

import os
import json
import asyncio
from typing import Callable, Optional
from aio_pika import connect, IncomingMessage, Connection, Channel, Queue

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.repositories import IMessageConsumer
from app.domain.models import EmbeddingTask

logger = get_logger(__name__)


class RabbitMQConsumer(IMessageConsumer):
    """RabbitMQ implementation of message consumer."""
    
    def __init__(self, message_handler: Callable[[EmbeddingTask], asyncio.coroutine]):
        """
        Initialize RabbitMQ consumer.
        
        Args:
            message_handler: Async function to handle received tasks
        """
        self.rabbitmq_url = settings.RABBITMQ_URL
        self.queue_name = settings.RABBITMQ_QUEUE
        self.queue_durable = settings.RABBITMQ_QUEUE_DURABLE
        self.message_handler = message_handler
        
        self._connection: Optional[Connection] = None
        self._channel: Optional[Channel] = None
        self._queue: Optional[Queue] = None
        self._consumer_tag: Optional[str] = None
        
        logger.info(f"Initialized RabbitMQ consumer for queue: {self.queue_name}")
    
    async def start(self):
        """Start consuming messages from RabbitMQ queue."""
        try:
            # Connect to RabbitMQ
            logger.info(f"Connecting to RabbitMQ: {self.rabbitmq_url}")
            self._connection = await connect(self.rabbitmq_url)
            self._channel = await self._connection.channel()
            
            # Declare queue
            self._queue = await self._channel.declare_queue(
                self.queue_name,
                durable=self.queue_durable
            )
            
            logger.info(f"Connected to queue: {self.queue_name}")
            logger.info("Waiting for messages. To exit press CTRL+C")
            
            # Start consuming
            await self._queue.consume(self._on_message)
            
        except Exception as e:
            logger.error(f"Failed to start consumer: {e}")
            raise
    
    async def stop(self):
        """Stop consuming messages and close connections."""
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
        Handle incoming RabbitMQ message.
        
        Args:
            message: Incoming message from queue
        """
        async with message.process():
            try:
                # Parse message body
                body = json.loads(message.body.decode())
                logger.info(f"Received message: {body}")
                
                # Create task model
                task = EmbeddingTask(
                    uuid=body.get("uuid"),
                    file_path=body.get("file_path"),
                    user_id=body.get("user_id"),
                    correlation_id=body.get("correlation_id")
                )
                
                # Set correlation ID for logging
                from app.core.logging import setup_logging
                correlation_filter = setup_logging(settings.LOG_LEVEL)
                correlation_filter.set_correlation_id(task.correlation_id)
                
                # Validate file exists
                if not os.path.exists(task.file_path):
                    logger.error(f"File not found: {task.file_path}")
                    return
                
                # Call handler
                await self.message_handler(task)
                
                logger.info(f"Successfully processed message for image: {task.uuid}")
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in message: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Message will be requeued if not acknowledged
