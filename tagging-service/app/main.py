from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
import io, httpx, os

from .infrastructure.config_loader import load_model_config, load_labels
from .services.tagger import TaggingService

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
    cfg = load_model_config()
    labels = load_labels(cfg["labels_path"])
    app.state.tagger = TaggingService(
        model_path=cfg["model_path"],
        labels=labels,
        input_size=cfg["input_size"],
        mean=cfg["mean"],
        std=cfg["std"],
        apply_softmax=cfg["apply_softmax"],
        default_top_k=cfg["top_k"],
    )

@app.get("/healthz")
async def health():
    return {
        "status": "ok",
        "model_path": os.getenv("MODEL_PATH"),
        "labels_path": os.getenv("LABELS_PATH")
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