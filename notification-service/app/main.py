import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
import aio_pika
from ws_manager import manager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification-service")

# 환경 변수
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq-broker")
RABBITMQ_URL = f"amqp://guest:guest@{RABBITMQ_HOST}/"

async def consume_events():
    """
    RabbitMQ의 'notifications' Exchange를 구독하고, 
    메시지가 오면 WebSocket으로 해당 유저에게 전송합니다.
    """
    connection = None
    try:
        # 1. RabbitMQ 연결
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()

        # 2. Exchange 선언 (Fanout 타입: 모든 큐에 브로드캐스트)
        # 다른 서비스(Tagging, CRUD)는 이 'notifications' exchange로 메시지를 보내야 함
        exchange = await channel.declare_exchange("notifications", aio_pika.ExchangeType.FANOUT)

        # 3. 임시 큐 생성 (Exclusive=True: 이 서비스가 꺼지면 큐도 삭제됨)
        queue = await channel.declare_queue(exclusive=True)
        await queue.bind(exchange)

        logger.info(" [*] Waiting for notification events...")

        # 4. 메시지 수신 루프
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        target_user_id = data.get("user_id")
                        
                        if target_user_id:
                            logger.info(f"[MQ Received] Event: {data.get('event')} -> User: {target_user_id}")
                            # WebSocket Manager에게 전달
                            await manager.broadcast(target_user_id, json.dumps(data))
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
    
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
    Nginx Gateway에서 인증을 마친 후 접속한다고 가정합니다.
    """
    # 보안 강화: 실제로는 Nginx가 헤더에 넣어준 X-User-ID와 
    # URL의 user_id가 일치하는지 검사하는 것이 좋습니다.
    # headers = websocket.headers
    # verified_id = headers.get("x-user-id")
    
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