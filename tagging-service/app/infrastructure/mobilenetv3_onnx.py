import onnxruntime as ort
import numpy as np
from PIL import Image

class MobileNetV3OnnxRunner:
    def __init__(self, model_path: str, input_size: int = 224, mean=(0.485,0.456,0.406), std=(0.229,0.224,0.225), apply_softmax=True):
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = input_size
        self.mean = np.array(mean, dtype=np.float32)
        self.std = np.array(std, dtype=np.float32)
        self.apply_softmax = apply_softmax

    def _preprocess(self, img: Image.Image):
        img = img.convert("RGB").resize((self.input_size, self.input_size))
        arr = np.asarray(img).astype(np.float32) / 255.0
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)
        return np.expand_dims(arr, 0)

    def predict(self, img: Image.Image):
        inp = self._preprocess(img)
        outputs = self.session.run(None, {self.input_name: inp})
        logits = outputs[0].squeeze()
        if self.apply_softmax:
            ex = np.exp(logits - np.max(logits))
            return ex / ex.sum()
        return logits