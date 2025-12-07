"""
모니터링 서비스로 로그를 발행하는 모듈
"""
import json
from typing import Optional
from datetime import datetime
import traceback

from .message_broker import MessageBroker
from ..core.logging import logger


class MonitoringPublisher:
    """모니터링 서비스로 로그 발행"""
    
    def __init__(self, message_broker: MessageBroker, service_name: str = "crud-service"):
        self.message_broker = message_broker
        self.service_name = service_name
    
    async def publish_system_log(
        self,
        correlation_id: str,
        message: str,
        log_level: str = "INFO"
    ):
        """시스템 로그 발행"""
        try:
            log_data = {
                "correlationId": correlation_id,
                "serviceName": self.service_name,
                "message": message,
                "logType": "SYSTEM",
                "logLevel": log_level
            }
            
            # main.exchange로 발행 (service.crud.info 등)
            routing_key = f"service.{self.service_name}.{log_level.lower()}"
            await self._publish_to_monitoring(routing_key, log_data)
            
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
        try:
            # 스택 트레이스 생성
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
            
            # main.exchange로 발행
            routing_key = f"service.{self.service_name}.error"
            await self._publish_to_monitoring(routing_key, log_data)
            
        except Exception as e:
            logger.error(f"Failed to publish error log: {e}")
    
    async def publish_retry_result(
        self,
        correlation_id: str,
        success: bool,
        message: str,
        exception: Optional[Exception] = None,
        stack_trace: Optional[str] = None
    ):
        """재시도 결과를 recovery.exchange로 발행"""
        try:
            # 스택 트레이스 생성
            if exception and not stack_trace:
                stack_trace = ''.join(traceback.format_exception(
                    type(exception),
                    exception,
                    exception.__traceback__
                ))
            
            result_data = {
                "correlationId": correlation_id,
                "serviceName": self.service_name,
                "message": message,
                "success": success,
                "logType": "RETRY_RESULT"
            }
            
            if not success:
                result_data["stackTrace"] = stack_trace or ""
                result_data["exceptionType"] = type(exception).__name__ if exception else "Unknown"
            
            # recovery.exchange로 발행 (routing_key: [service].retry.success 또는 [service].retry.error)
            status = "success" if success else "error"
            routing_key = f"{self.service_name}.retry.{status}"
            await self._publish_to_recovery(routing_key, result_data)
            
        except Exception as e:
            logger.error(f"Failed to publish retry result: {e}")
    
    async def _publish_to_monitoring(self, routing_key: str, log_data: dict):
        """main.exchange로 메시지 발행"""
        if not self.message_broker.channel:
            logger.warning("RabbitMQ channel not available for monitoring")
            return
        
        try:
            import aio_pika
            
            # main.exchange 선언
            exchange = await self.message_broker.channel.declare_exchange(
                "main.exchange",
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # 메시지 생성
            message = aio_pika.Message(
                body=json.dumps(log_data).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            
            # 메시지 발행
            await exchange.publish(message, routing_key=routing_key)
            logger.debug(f"[Monitoring] Published to main.exchange: {routing_key}")
        
        except Exception as e:
            logger.error(f"Failed to publish to main.exchange: {e}")
    
    async def _publish_to_recovery(self, routing_key: str, log_data: dict):
        """recovery.exchange로 메시지 발행"""
        if not self.message_broker.channel:
            logger.warning("RabbitMQ channel not available for monitoring")
            return
        
        try:
            import aio_pika
            
            # recovery.exchange 선언
            exchange = await self.message_broker.channel.declare_exchange(
                "recovery.exchange",
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # 메시지 생성
            message = aio_pika.Message(
                body=json.dumps(log_data).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            
            # 메시지 발행
            await exchange.publish(message, routing_key=routing_key)
            logger.debug(f"[Monitoring] Published to recovery.exchange: {routing_key}")
        
        except Exception as e:
            logger.error(f"Failed to publish to recovery.exchange: {e}")
