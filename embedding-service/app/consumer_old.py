# src/consumer.py
import json
import os
import sys
import asyncio
from aio_pika import connect, IncomingMessage

# 리팩토링한 모듈들 가져오기
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import settings
from pinecone_manager import pinecone_db
from koclip_model import embedder

# RabbitMQ 연결 설정 (환경변수나 config에서 가져오기)
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

async def on_message(message: IncomingMessage):
    """
    RabbitMQ에서 메시지가 오면 실행되는 함수
    메시지 예시: {"uuid": "img_001", "file_path": "/app/uploads/cat.jpg", "user_id": "user_1"}
    """
    async with message.process():
        try:
            # 1. 메시지 파싱
            body = json.loads(message.body)
            print(f" [x] Received message: {body}")

            image_uuid = body.get("uuid")
            file_path = body.get("file_path") # 중요: 공유 볼륨 경로 (/app/uploads/...)
            user_id = body.get("user_id")

            # 2. 파일 존재 확인 (Claim Check Pattern)
            if not os.path.exists(file_path):
                print(f" [!] File not found: {file_path}")
                return

            # 3. AI 모델로 임베딩 생성 (리팩토링한 모듈 사용)
            print(f" ... Generating embedding for {file_path}")
            vector_values = embedder.encode_image(file_path)

            # 4. Pinecone에 저장 (리팩토링한 모듈 사용)
            metadata = {
                "userid": user_id,
                "filename": os.path.basename(file_path),
                "path": file_path
            }
            
            pinecone_db.upsert_vector(
                vector_id=image_uuid, 
                vector=vector_values, 
                metadata=metadata
            )
            
            print(f" [v] Successfully stored vector for {image_uuid}")

        except Exception as e:
            print(f" [!] Error processing message: {e}")
            # 필요 시 에러 큐로 보내거나 재시도 로직 추가

async def main():
    # RabbitMQ 연결
    connection = await connect(RABBITMQ_URL)
    channel = await connection.channel()

    # 큐 선언 (Sync Service가 보내는 큐 이름과 같아야 함)
    queue = await channel.declare_queue("image_embedding_queue", durable=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    
    # 메시지 소비 시작
    await queue.consume(on_message)

    # 무한 대기
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())