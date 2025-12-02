"""
애플리케이션 설정 관리
"""
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # Database
    db_host: str = "crud-mysql-db"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str 
    db_name: str = "crud_db"
    
    # Redis
    redis_host: str = "crud-redis-cache"
    redis_port: int = 6379
    
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"
    
    # RabbitMQ
    rabbitmq_host: str = "rabbitmq-broker"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = Field(..., alias="RABBITMQ_USER")
    rabbitmq_password: str = Field(..., alias="RABBITMQ_PASS")
    
    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@"
            f"{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )
    
    # JWT
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    
    # Server
    server_url: str = "http://localhost:8576"
    
    # Storage
    shared_image_dir: str = "/app/shared_images"
    
    @property
    def upload_dir(self) -> str:
        return os.path.join(self.shared_image_dir, "uploads")
    
    @property
    def original_dir(self) -> str:
        return os.path.join(self.upload_dir, "original")
    
    @property
    def thumbnail_dir(self) -> str:
        return os.path.join(self.upload_dir, "thumbnail")
    
    # Queue names
    token_verify_queue: str = "token_verify_queue"
    token_verify_response_queue: str = "token_verify_response_queue"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )


settings = Settings()
