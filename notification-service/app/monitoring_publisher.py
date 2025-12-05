"""
모니터링 서비스로 로그를 발행하는 모듈
"""
import json
from typing import Optional
import traceback
import logging

logger = logging.getLogger("notification-service")


class MonitoringPublisher:
    """모니터링 서비스로 로그 발행 (RabbitMQ)"""
    
    def __init__(self, service_name: str = "notification-service"):
        self.service_name = service_name
        self.channel = None
        self.exchange = None
    
    async def connect(self, channel):
        """RabbitMQ 채널 설정"""
        import aio_pika
        
        self.channel = channel
        self.exchange = await channel.declare_exchange(
            "main.exchange",
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        logger.info("MonitoringPublisher connected to RabbitMQ")
    
    async def publish_system_log(
        self,
        correlation_id: str,
        message: str,
        log_level: str = "INFO"
    ):
        """시스템 로그 발행"""
        if not self.channel:
            logger.warning("MonitoringPublisher not connected")
            return
        
        try:
            log_data = {
                "correlationId": correlation_id,
                "serviceName": self.service_name,
                "message": message,
                "logType": "SYSTEM",
                "logLevel": log_level
            }
            
            routing_key = f"service.{self.service_name}.{log_level.lower()}"
            await self._publish(routing_key, log_data)
            
        except Exception as e:
            logger.error(f"Failed to publish system log: {e}")
    
    async def publish_error_log(
        self,
        correlation_id: str,
        message: str,
        exception: Optional[Exception] = None,
        stack_trace: Optional[str] = None
    ):
        """에러 로그 발행"""
        if not self.channel:
            logger.warning("MonitoringPublisher not connected")
            return
        
        try:
            if exception and not stack_trace:
                stack_trace = ''.join(traceback.format_exception(
                    type(exception),
                    exception,
                    exception.__traceback__
                ))
            
            log_data = {
                "correlationId": correlation_id,
                "serviceName": self.service_name,
                "message": message,
                "logType": "ERROR",
                "stackTrace": stack_trace or "",
                "exceptionType": type(exception).__name__ if exception else "Unknown"
            }
            
            routing_key = f"service.{self.service_name}.error"
            await self._publish(routing_key, log_data)
            
        except Exception as e:
            logger.error(f"Failed to publish error log: {e}")
    
    async def _publish(self, routing_key: str, log_data: dict):
        """메시지 발행"""
        import aio_pika
        
        message = aio_pika.Message(
            body=json.dumps(log_data).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        
        await self.exchange.publish(message, routing_key=routing_key)
        logger.debug(f"[Monitoring] Published: {routing_key}")
