"""
Message consumer entry point
RabbitMQ로부터 이미지 업로드 이벤트를 받아 자동 태깅 수행
"""
import asyncio
import aio_pika
import json
from app.infrastructure.message_consumer import RabbitMQConsumer
from app.infrastructure.database import init_db, close_db, get_db
from app.infrastructure.repositories import TagRepository, DataTagRepository
from app.services.tagging_service import TaggingService  # DB 저장 기능 포함
from app.domain.models import TaggingTask
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.labels import load_labels

logger = get_logger(__name__)

# 글로벌 태깅 서비스 (DB 저장 기능 포함)
tagging_service: TaggingService = None
rabbitmq_connection = None


async def publish_tagging_completed(data_id: str, user_id: str, tags: list):
    """
    태깅 완료 이벤트를 RabbitMQ로 발행
    notification-service가 이를 받아 Electron으로 WebSocket 전송
    """
    global rabbitmq_connection
    try:
        if not rabbitmq_connection:
            logger.warning("RabbitMQ connection not available for publish")
            return
            
        channel = await rabbitmq_connection.channel()
        exchange = await channel.declare_exchange(
            "crud_events",
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        
        message_body = {
            "event": "tagging:completed",
            "data_id": data_id,
            "user_id": user_id,
            "tags": [{"name": t[0], "score": t[1], "source": "auto"} for t in tags]
        }
        
        await exchange.publish(
            aio_pika.Message(body=json.dumps(message_body).encode()),
            routing_key="crud.tagging_completed"
        )
        
        logger.info(f"Published tagging:completed event for data_id: {data_id}")
        await channel.close()
        
    except Exception as e:
        logger.error(f"Failed to publish tagging completed event: {e}", exc_info=True)


async def handle_tagging_task(task: TaggingTask):
    """
    태깅 작업 처리 핸들러
    
    Args:
        task: 태깅 작업 정보
    """
    global tagging_service
    
    try:
        # DB 세션 획득
        async for session in get_db():
            # 리포지토리 생성
            tag_repo = TagRepository(session)
            data_tag_repo = DataTagRepository(session)
            
            # 태깅 및 DB 저장
            tags = await tagging_service.process_and_save_tags(
                task=task,
                tag_repo=tag_repo,
                data_tag_repo=data_tag_repo
            )
            
            logger.info(f"Task completed for data_id: {task.data_id}, tags: {[t[0] for t in tags]}")
            
            # 태깅 완료 이벤트 발행
            await publish_tagging_completed(
                data_id=task.data_id,
                user_id=task.user_id,
                tags=tags
            )
            
    except Exception as e:
        logger.error(f"Failed to handle tagging task: {e}", exc_info=True)


async def run_consumer():
    """메시지 컨슈머 실행"""
    global tagging_service, rabbitmq_connection
    
    try:
        # 데이터베이스 초기화
        logger.info("Initializing database...")
        await init_db()
        
        # RabbitMQ 연결 (발행용)
        logger.info("Connecting to RabbitMQ for publishing...")
        rabbitmq_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        
        # 태깅 서비스 초기화
        logger.info("Initializing tagging service...")
        labels = load_labels(settings.LABELS_PATH)
        tagging_service = TaggingService(
            model_path=settings.MODEL_PATH,
            labels=labels,
            input_size=224,
            mean=(0.485, 0.456, 0.406),
            std=(0.229, 0.224, 0.225),
            apply_softmax=True,
        )
        
        # RabbitMQ 컨슈머 시작
        logger.info("Starting RabbitMQ consumer...")
        consumer = RabbitMQConsumer(message_handler=handle_tagging_task)
        await consumer.start()
        
        # 무한 대기
        try:
            await asyncio.Future()  # run forever
        except asyncio.CancelledError:
            logger.info("Consumer cancelled")
        finally:
            await consumer.stop()
            if rabbitmq_connection:
                await rabbitmq_connection.close()
            await close_db()
            
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
        if rabbitmq_connection:
            await rabbitmq_connection.close()
        await close_db()
        raise


if __name__ == "__main__":
    asyncio.run(run_consumer())
