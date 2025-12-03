from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
import io, httpx, os

from .infrastructure.labels import load_labels
from .services.tagger import TaggingService  # HTTP API용 (DB 저장 없음)
from .core.config import settings
from .infrastructure.database import init_db, close_db

app = FastAPI(title="Tagging Service", version="1.0.0")

class UrlTagRequest(BaseModel):
    url: str
    top_k: Optional[int] = None

class Tag(BaseModel):
    label: str
    score: float

class TagResponse(BaseModel):
    tags: List[Tag]

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화"""
    # 데이터베이스 초기화
    await init_db()
    
    # HTTP API용 태거 초기화 (DB 저장 없음)
    labels = load_labels(settings.LABELS_PATH)
    app.state.tagger = TaggingService(
        model_path=settings.MODEL_PATH,
        labels=labels,
        input_size=224,
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
        apply_softmax=True,
        default_top_k=settings.TOP_K,
    )

@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리"""
    await close_db()

@app.get("/healthz")
async def health():
    return {
        "status": "ok",
        "model_path": settings.MODEL_PATH,
        "labels_path": settings.LABELS_PATH
    }

@app.post("/tag/image", response_model=TagResponse)
async def tag_image(file: UploadFile = File(...), top_k: Optional[int] = None):
    if not file.content_type or "image" not in file.content_type:
        raise HTTPException(status_code=400, detail="file must be an image")
    content = await file.read()
    img = Image.open(io.BytesIO(content)).convert("RGB")
    tags = app.state.tagger.predict_pil(img, top_k=top_k)
    return {"tags": [{"label": l, "score": s} for l, s in tags]}

@app.post("/tag/url", response_model=TagResponse)
async def tag_url(req: UrlTagRequest):
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(req.url)
            r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to load image: {e}")
    tags = app.state.tagger.predict_pil(img, top_k=req.top_k)
    return {"tags": [{"label": l, "score": s} for l, s in tags]}