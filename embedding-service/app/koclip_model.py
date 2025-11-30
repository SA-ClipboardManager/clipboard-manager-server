# koclip_model.py
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

class KoCLIPEmbedder:
    def __init__(self):
        self.repo = "Bingsu/clip-vit-large-patch14-ko"
        self.device = "cpu"  # 필요 시 "cuda"로 변경
        print(f"Loading KoCLIP model from {self.repo}...")
        self.model = CLIPModel.from_pretrained(self.repo).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(self.repo, use_fast=False)

    def encode_text(self, text: str) -> list:
        """텍스트를 입력받아 벡터 리스트(float list)로 반환"""
        inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True)
        for k in inputs:
            inputs[k] = inputs[k].to(self.device)
        
        with torch.inference_mode():
            outputs = self.model.get_text_features(**inputs)
        
        # Tensor -> List 변환하여 반환
        return outputs[0].tolist()

    def encode_image(self, image_path: str) -> list:
        """이미지 경로를 받아 벡터 리스트(float list)로 반환"""
        image = Image.open(image_path).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        for k in inputs:
            inputs[k] = inputs[k].to(self.device)
            
        with torch.inference_mode():
            outputs = self.model.get_image_features(**inputs)
            
        return outputs[0].tolist()

# 인스턴스 생성
embedder = KoCLIPEmbedder()