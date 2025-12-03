from typing import List, Tuple, Optional
import os
import numpy as np
from PIL import Image
from ..infrastructure.mobilenetv3_onnx import MobileNetV3OnnxRunner

# Deprecated: prefer app.services.tagging_service.TaggingService
class TaggingService:
    def __init__(
        self,
        model_path: str,
        labels: List[str],
        input_size: int = 224,
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
        apply_softmax=True,
        min_score: Optional[float] = None,
    ):
        self.runner = MobileNetV3OnnxRunner(model_path, input_size, mean, std, apply_softmax)
        self.labels = labels
        try:
            env_min = os.getenv("TAGGING_MIN_SCORE")
            self.min_score = float(env_min) if env_min is not None else (min_score if min_score is not None else 0.5)
        except ValueError:
            self.min_score = min_score if min_score is not None else 0.5

    def predict_pil(self, img: Image.Image, top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        probs = self.runner.predict(img)
        sorted_idx = np.argsort(-probs)
        results: List[Tuple[str, float]] = []
        for i in sorted_idx:
            score = float(probs[i])
            if score < self.min_score:
                continue
            label = self.labels[i] if i < len(self.labels) else f"class_{i}"
            results.append((label, score))
        if top_k is not None:
            return results[: top_k]
        return results