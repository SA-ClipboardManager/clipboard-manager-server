"""
Message consumer entry point
RabbitMQ로부터 이미지 업로드 이벤트를 받아 자동 태깅 수행
"""
import asyncio
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
            
    except Exception as e:
        logger.error(f"Failed to handle tagging task: {e}", exc_info=True)


async def run_consumer():
    """메시지 컨슈머 실행"""
    global tagging_service
    
    try:
        # 데이터베이스 초기화
        logger.info("Initializing database...")
        await init_db()
        
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
            default_top_k=settings.TOP_K
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
            await close_db()
            
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
        await close_db()
        raise


if __name__ == "__main__":
    asyncio.run(run_consumer())
