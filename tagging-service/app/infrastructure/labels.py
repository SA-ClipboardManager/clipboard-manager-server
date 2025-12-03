import os, json, ast
from typing import List, Dict, Any

def load_labels(path: str) -> List[str]:
    if path.endswith(".txt"):
        with open(path, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "classes" in data:
                return list(map(str, data["classes"]))
            if isinstance(data, list):
                return list(map(str, data))
    if path.endswith(".py"):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.lower() == "classes":
                        val = ast.literal_eval(node.value)
                        return list(map(str, val))
    raise ValueError(f"Unsupported labels file: {path}")

def load_model_config() -> Dict[str, Any]:
    return {
        "model_path": os.getenv("MODEL_PATH", "/models/mobilenetv3/model.onnx"),
        "labels_path": os.getenv("LABELS_PATH", "/models/mobilenetv3/Classes.py"),
        "input_size": int(os.getenv("MODEL_INPUT_SIZE", "224")),
        "mean": tuple(map(float, os.getenv("MODEL_MEAN", "0.485,0.456,0.406").split(","))),
        "std": tuple(map(float, os.getenv("MODEL_STD", "0.229,0.224,0.225").split(","))),
        "apply_softmax": os.getenv("MODEL_SOFTMAX", "true").lower() == "true",
        "top_k": int(os.getenv("TOP_K", "5")),
    }