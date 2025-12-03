"""
Embedding Service Startup Script
Runs both FastAPI server and RabbitMQ consumer concurrently
"""

import asyncio
import signal
import sys
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.core.logging import setup_logging, get_logger


# Setup logging
correlation_filter = setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


async def run_api_server():
    """Run FastAPI server"""
    import uvicorn
    
    config = uvicorn.Config(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower()
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_consumer():
    """Run RabbitMQ consumer"""
    from app.consumer import main as consumer_main
    await consumer_main()


async def main():
    """Main entry point - runs both API and consumer"""
    logger.info("=" * 60)
    logger.info("Starting Embedding Service (API + Consumer)")
    logger.info(f"API: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"Consumer Queue: {settings.RABBITMQ_IMAGE_QUEUE}")
    logger.info("=" * 60)
    
    # Create tasks for both services
    api_task = asyncio.create_task(run_api_server())
    consumer_task = asyncio.create_task(run_consumer())
    
    # Setup graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        api_task.cancel()
        consumer_task.cancel()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Wait for both tasks
        await asyncio.gather(api_task, consumer_task)
    except asyncio.CancelledError:
        logger.info("Services cancelled")
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        logger.info("Embedding Service shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
