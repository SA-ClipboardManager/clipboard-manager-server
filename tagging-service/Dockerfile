FROM python:3.11-slim
# FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드
COPY app ./app

# 모델/라벨을 이미지에 포함 (tagging-service/models 디렉터리에 미리 추가)
COPY models/mobilenetv3_trained.onnx /app/models/mobilenetv3_trained.onnx
COPY models/Classes.py /app/models/Classes.py

# 기본 환경변수(컴포즈에서 override 가능)
ENV MODEL_PATH=/app/models/mobilenetv3_trained.onnx \
    LABELS_PATH=/app/models/Classes.py \
    TOP_K=5

EXPOSE 8000

# FastAPI 서버와 Consumer를 함께 실행
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port 8000 & python -m app.consumer"
