"""Monitoring publisher singleton provider."""
from .message_broker import message_broker
from .monitoring_publisher import MonitoringPublisher

monitoring_publisher = MonitoringPublisher(message_broker, "crud-service")
