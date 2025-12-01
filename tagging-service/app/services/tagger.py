from typing import List, Tuple, Optional
import numpy as np
from PIL import Image
from ..infrastructure.mobilenetv3_onnx import MobileNetV3OnnxRunner

class TaggingService:
    def __init__(self, model_path: str, labels: List[str], input_size: int = 224,
                 mean=(0.485,0.456,0.406), std=(0.229,0.224,0.225),
                 apply_softmax=True, default_top_k: int = 5):
        self.runner = MobileNetV3OnnxRunner(model_path, input_size, mean, std, apply_softmax)
        self.labels = labels
        self.default_top_k = default_top_k

    def predict_pil(self, img: Image.Image, top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        probs = self.runner.predict(img)
        k = top_k or self.default_top_k
        k = min(k, probs.shape[-1])
        idx = np.argsort(-probs)[:k]
        return [(self.labels[i] if i < len(self.labels) else f"class_{i}", float(probs[i])) for i in idx]