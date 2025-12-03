"""
Core configuration settings
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # MySQL 설정
    MYSQL_HOST: str = "tagging-mysql-db"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "tagging_db"
    
    # RabbitMQ 설정
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    RABBITMQ_QUEUE: str = "tagging_queue"
    RABBITMQ_QUEUE_DURABLE: bool = True
    RABBITMQ_EXCHANGE: str = "crud_events"
    RABBITMQ_ROUTING_KEY: str = "crud:imgSave_success"
    
    # 모델 설정
    MODEL_PATH: str = "/app/models/mobilenetv3_trained.onnx"
    LABELS_PATH: str = "/app/models/Classes.py"
    TOP_K: int = 5
    
    @property
    def rabbitmq_url(self) -> str:
        """RabbitMQ 연결 URL"""
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
    
    @property
    def mysql_url(self) -> str:
        """MySQL 연결 URL"""
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
