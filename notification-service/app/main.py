import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aio_pika
import jwt
from ws_manager import manager
from monitoring_publisher import MonitoringPublisher

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification-service")

# 모니터링 퍼블리셔 인스턴스
monitoring_publisher = None

# 환경 변수
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq-broker")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"

def verify_token(token: str) -> str:
    """토큰을 검증하고 user_id를 반환합니다."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


async def consume_events():
    global monitoring_publisher
    url=f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}/"
    connection = None
    try:
        # 1. RabbitMQ 연결
        for i in range(15): # Retry for 30 seconds
            try:
                connection = await aio_pika.connect_robust(url, reconnect_interval=5)
                logger.info("Successfully connected to RabbitMQ.")
                break
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"Connecting to RabbitMQ failed (attempt {i+1}/15), retrying in 2 seconds...")
                if i == 14:
                    logger.error("Could not connect to RabbitMQ after all retries.")
                    raise e
                await asyncio.sleep(2)
        
        if connection is None:
            # This should not be reached if the loop raises an exception, but as a safeguard:
            logger.error("Failed to establish RabbitMQ connection.")
            return

        channel = await connection.channel()
        
        # 모니터링 퍼블리셔 초기화
        monitoring_publisher = MonitoringPublisher("notification-service")
        await monitoring_publisher.connect(channel)
        logger.info("MonitoringPublisher initialized")

        # 2-1. Fanout Exchange 선언 (기존 notifications) - 사용 안 함
        # notifications_exchange = await channel.declare_exchange("notifications", aio_pika.ExchangeType.FANOUT)
        
        # 2-2. Topic Exchange 선언 (main.exchange - 모니터링 서비스 규격)
        main_exchange = await channel.declare_exchange("main.exchange", aio_pika.ExchangeType.TOPIC, durable=True)
        
        # 2-3. Topic Exchange 선언 (recovery.exchange - 재시도 요청)
        recovery_exchange = await channel.declare_exchange("recovery.exchange", aio_pika.ExchangeType.TOPIC, durable=True)

        # 3. 임시 큐 생성 (Exclusive=True: 이 서비스가 꺼지면 큐도 삭제됨)
        queue = await channel.declare_queue(exclusive=True)
        
        # 4. Exchange 바인딩 (main.exchange와 recovery.exchange 모두 사용)
        # await queue.bind(notifications_exchange)  # 중복 수신 방지를 위해 제거
        await queue.bind(main_exchange, routing_key="service.#")  # main.exchange의 모든 service.* 이벤트
        await queue.bind(recovery_exchange, routing_key="notification-service.do.retry")  # recovery.exchange의 재시도 요청

        logger.info(" [*] Waiting for notification events (main.exchange + recovery.exchange)...")

        # 5. 메시지 수신 루프
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        event_type = data.get("event")
                        # 두 가지 메시지 형식 모두 지원:
                        # 1. 기존 형식: {event, data: {user_id, ...}}
                        # 2. EventDataDto 형식: {correlationId, serviceName, dataId, userId, ...}
                        inner_data = data.get("data", data)  # 'data' 필드가 있으면 사용, 없으면 전체 사용
                        target_user_id = inner_data.get("user_id") or inner_data.get("userId")

                        
                        # 재시도 요청 감지
                        is_retry_request = event_type and "notification-service.do.retry" in event_type
                        
                        # routing_key 기반 이벤트 타입 감지 (event 필드 없을 때의 backup)
                        if not event_type and message.routing_key:
                            event_type = message.routing_key
                            logger.info(f"[MQ] Event type from routing_key: {event_type}")

                        if target_user_id:
                            logger.info(f"[MQ Received] {'Retry request' if is_retry_request else 'Event'}: {event_type} -> User: {target_user_id}")
                            
                            try:
                                # WebSocket으로 전달할 메시지 구성
                                # service.tagging.success/error 이벤트의 경우 tagging_result로 변환
                                if "tagging" in str(event_type):
                                    # EventDataDto 형식에서 필요한 필드 추출
                                    ws_message = {
                                        "type": "tagging_result",
                                        "event": event_type,
                                        "data_id": inner_data.get("dataId"),  # ✅ data_id로 변환
                                        "user_id": target_user_id,
                                        "tags": inner_data.get("tags", []),
                                        "file_path": inner_data.get("filePath"),
                                        "model_source": inner_data.get("modelSource"),
                                        "correlation_id": inner_data.get("correlationId"),
                                    }
                                    logger.info(f"[MQ Tagging] Converted to WS format: dataId={ws_message.get('data_id')}, tags count={len(ws_message.get('tags', []))}")
                                else:
                                    ws_message = {
                                        "type": event_type,
                                        "event": event_type,
                                        **inner_data
                                    }

                                
                                # WebSocket Manager에게 전달
                                await manager.broadcast(target_user_id, json.dumps(ws_message))
                                
                                # 재시도 요청인 경우 성공 결과 발행
                                if is_retry_request and monitoring_publisher:
                                    await monitoring_publisher.publish_retry_result(
                                        correlation_id=inner_data.get("correlationId") or data.get("correlation_id", event_type),
                                        success=True,
                                        message=f"Retry successful: notification sent to user {target_user_id}"
                                    )
                                # 일반 요청 성공 로그 발행
                                elif monitoring_publisher:
                                    await monitoring_publisher.publish_system_log(
                                        correlation_id=inner_data.get("correlationId") or inner_data.get("correlation_id") or data.get("correlation_id", "unknown"),
                                        message=f"Notification sent successfully to user {target_user_id} (event: {event_type})",
                                        log_level="INFO"
                                    )
                                    
                            except Exception as send_error:
                                logger.error(f"Failed to send notification: {send_error}")
                                
                                # 재시도 요청인 경우 실패 결과 발행
                                if is_retry_request and monitoring_publisher:
                                    await monitoring_publisher.publish_retry_result(
                                        correlation_id=inner_data.get("correlationId") or data.get("correlation_id", event_type),
                                        success=False,
                                        message=f"Retry failed: could not send notification",
                                        exception=send_error
                                    )
                                else:
                                    # 일반 요청 실패는 에러 로그로
                                    if monitoring_publisher:
                                        await monitoring_publisher.publish_error_log(
                                            correlation_id=inner_data.get("correlationId") or inner_data.get("correlation_id") or data.get("correlation_id", "unknown"),
                                            message=f"Failed to send notification",
                                            exception=send_error
                                        )
                        else:
                            logger.warning(f"[MQ Received] No user_id in event: {event_type}, data={inner_data}")

                            
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        
                        # 모니터링 에러 로그 발행
                        if monitoring_publisher:
                            correlation_id = inner_data.get("correlationId") if 'inner_data' in locals() else "unknown"
                            is_retry = 'is_retry_request' in locals() and locals()['is_retry_request']
                            
                            if is_retry:
                                # 재시도 요청 처리 중 에러
                                await monitoring_publisher.publish_retry_result(
                                    correlation_id=correlation_id,
                                    success=False,
                                    message=f"Failed to process retry request",
                                    exception=e
                                )
                            else:
                                # 일반 메시지 처리 중 에러
                                await monitoring_publisher.publish_error_log(
                                    correlation_id=correlation_id,
                                    message=f"Failed to process notification message",
                                    exception=e
                                )
    
    except asyncio.CancelledError:
        logger.info("Consumer task cancelled.")
    except Exception as e:
        logger.error(f"RabbitMQ connection failed: {e}")
    finally:
        if connection:
            await connection.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 백그라운드 태스크로 RabbitMQ Consumer 실행
    task = asyncio.create_task(consume_events())
    yield
    # 앱 종료 시 태스크 취소
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    클라이언트가 연결하는 웹소켓 엔드포인트
    Authorization 헤더로 토큰을 검증합니다.
    """
    # Authorization 헤더에서 토큰 추출
    auth_header = websocket.headers.get("authorization")
    logger.info(f"WebSocket attempt: user_id={user_id}, auth={auth_header is not None}")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid Authorization header")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    token = auth_header.split(" ")[1]
    
    try:
        verified_user_id = verify_token(token)
        logger.info(f"Token verified: {verified_user_id}")
        # URL의 user_id와 토큰의 user_id가 일치하는지 확인
        if verified_user_id != user_id:
            logger.warning(f"User ID mismatch: token={verified_user_id}, url={user_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except HTTPException as e:
        logger.warning(f"Token verification failed: {e.detail}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    except Exception as e:
        logger.error(f"Token error: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    await manager.connect(user_id, websocket)
    try:
        while True:
            # 클라이언트로부터 메시지를 받을 일은 거의 없지만(단방향 알림 위주),
            # 연결 유지를 위해 대기합니다.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)
