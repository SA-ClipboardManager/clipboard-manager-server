FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 모델 다운로드용 캐시 디렉토리
ENV TRANSFORMERS_CACHE=/app/cache
RUN mkdir -p /app/cache
    
# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사 (Clean Architecture structure)
COPY app/ ./app/

# Uvicorn 서버 실행 명령어 (FastAPI 실행)
# To run consumer instead: CMD ["python", "app/consumer.py"]
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]