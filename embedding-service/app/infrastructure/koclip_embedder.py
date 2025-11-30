"""
KoCLIP embedding model implementation.
Handles text and image encoding using the KoCLIP model.
"""

import asyncio
from typing import List
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.repositories import IEmbeddingModel

logger = get_logger(__name__)


class KoCLIPEmbedder(IEmbeddingModel):
    """KoCLIP model implementation for generating embeddings."""
    
    def __init__(self):
        """Initialize KoCLIP model and processor."""
        self.repo = settings.KOCLIP_MODEL_REPO
        self.device = settings.KOCLIP_DEVICE
        self._model = None
        self._processor = None
        logger.info(f"Initializing KoCLIP model from {self.repo} on {self.device}")
    
    def _load_model(self):
        """Load model and processor (lazy initialization)."""
        if self._model is None:
            logger.info("Loading KoCLIP model...")
            self._model = CLIPModel.from_pretrained(self.repo).to(self.device)
            self._processor = CLIPProcessor.from_pretrained(self.repo, use_fast=False)
            logger.info("KoCLIP model loaded successfully")
    
    async def encode_text(self, text: str) -> List[float]:
        """
        Encode text to vector representation.
        
        Args:
            text: Input text to encode
            
        Returns:
            Vector representation as list of floats
        """
        try:
            # Lazy load model
            if self._model is None:
                self._load_model()
            
            # Run encoding in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            vector = await loop.run_in_executor(
                None,
                self._encode_text_sync,
                text
            )
            
            logger.debug(f"Encoded text to vector (dim: {len(vector)})")
            return vector
            
        except Exception as e:
            logger.error(f"Failed to encode text: {e}")
            raise
    
    def _encode_text_sync(self, text: str) -> List[float]:
        """Synchronous text encoding (run in thread pool)."""
        inputs = self._processor(
            text=[text],
            return_tensors="pt",
            padding=True,
            truncation=True
        )
        
        # Move to device
        for k in inputs:
            inputs[k] = inputs[k].to(self.device)
        
        # Generate embeddings
        with torch.inference_mode():
            outputs = self._model.get_text_features(**inputs)
        
        # Convert to list
        return outputs[0].tolist()
    
    async def encode_image(self, image_path: str) -> List[float]:
        """
        Encode image to vector representation.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Vector representation as list of floats
        """
        try:
            # Lazy load model
            if self._model is None:
                self._load_model()
            
            # Run encoding in thread pool
            loop = asyncio.get_event_loop()
            vector = await loop.run_in_executor(
                None,
                self._encode_image_sync,
                image_path
            )
            
            logger.debug(f"Encoded image to vector (dim: {len(vector)})")
            return vector
            
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            raise
    
    def _encode_image_sync(self, image_path: str) -> List[float]:
        """Synchronous image encoding (run in thread pool)."""
        # Load and preprocess image
        image = Image.open(image_path).convert("RGB")
        
        inputs = self._processor(
            images=image,
            return_tensors="pt"
        )
        
        # Move to device
        for k in inputs:
            inputs[k] = inputs[k].to(self.device)
        
        # Generate embeddings
        with torch.inference_mode():
            outputs = self._model.get_image_features(**inputs)
        
        # Convert to list
        return outputs[0].tolist()
