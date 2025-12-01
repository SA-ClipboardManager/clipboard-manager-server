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
COPY models/mobilenetv3_trained.onnx /models/mobilenetv3/model.onnx
COPY models/Classes.py /models/mobilenetv3/Classes.py

# 기본 환경변수(컴포즈에서 override 가능)
ENV MODEL_PATH=/models/mobilenetv3/model.onnx \
    LABELS_PATH=/models/mobilenetv3/Classes.py \
    MODEL_INPUT_SIZE=224 \
    MODEL_MEAN=0.485,0.456,0.406 \
    MODEL_STD=0.229,0.224,0.225 \
    MODEL_SOFTMAX=true \
    TOP_K=5

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]