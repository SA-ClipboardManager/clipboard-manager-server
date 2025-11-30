"""
Configuration management for Embedding Service.
Loads settings from environment variables with validation.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Pinecone Configuration
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "images"
    PINECONE_DIMENSION: int = 768  # KoCLIP dimension
    PINECONE_METRIC: str = "cosine"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    
    # KoCLIP Model Configuration
    KOCLIP_MODEL_REPO: str = "Bingsu/clip-vit-large-patch14-ko"
    KOCLIP_DEVICE: str = "cpu"  # "cuda" for GPU
    
    # RabbitMQ Configuration
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    RABBITMQ_QUEUE: str = "image_embedding_queue"
    RABBITMQ_QUEUE_DURABLE: bool = True
    
    # Shared Storage
    SHARED_IMAGES_PATH: str = "/app/shared_images"
    
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8002
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
