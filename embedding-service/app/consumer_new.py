"""
RabbitMQ consumer application for Embedding Service.
Processes image embedding tasks from the message queue.
"""

import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.infrastructure.message_consumer import RabbitMQConsumer
from app.api.dependencies import get_embedding_service


# Setup logging
correlation_filter = setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


# Global consumer instance
consumer: RabbitMQConsumer = None


async def handle_embedding_task(task):
    """
    Handler function for embedding tasks.
    Called by the consumer for each message.
    """
    embedding_service = get_embedding_service()
    await embedding_service.process_embedding_task(task)


async def main():
    """Main consumer application."""
    global consumer
    
    logger.info("=" * 60)
    logger.info("Starting Embedding Service Consumer")
    logger.info(f"RabbitMQ URL: {settings.RABBITMQ_URL}")
    logger.info(f"Queue: {settings.RABBITMQ_QUEUE}")
    logger.info(f"Pinecone Index: {settings.PINECONE_INDEX_NAME}")
    logger.info(f"KoCLIP Model: {settings.KOCLIP_MODEL_REPO}")
    logger.info("=" * 60)
    
    # Create consumer
    consumer = RabbitMQConsumer(message_handler=handle_embedding_task)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start consuming
        await consumer.start()
        
        # Keep running
        await asyncio.Future()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Consumer error: {e}")
        raise
    finally:
        await shutdown()


async def shutdown():
    """Graceful shutdown handler."""
    global consumer
    
    logger.info("Shutting down consumer...")
    
    if consumer:
        await consumer.stop()
    
    logger.info("Consumer shutdown complete")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
