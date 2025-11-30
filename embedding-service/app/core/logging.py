"""
Structured logging configuration for Embedding Service.
Supports correlation ID tracking across requests.
"""

import logging
import sys
from typing import Optional
from datetime import datetime


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""
    
    def __init__(self):
        super().__init__()
        self.correlation_id: Optional[str] = None
    
    def filter(self, record):
        record.correlation_id = self.correlation_id or "N/A"
        return True
    
    def set_correlation_id(self, correlation_id: Optional[str]):
        """Set the correlation ID for subsequent log records."""
        self.correlation_id = correlation_id


class StructuredFormatter(logging.Formatter):
    """Format logs with structured information."""
    
    def format(self, record):
        # Add timestamp
        record.timestamp = datetime.utcnow().isoformat()
        
        # Format the message
        log_format = (
            "[%(timestamp)s] [%(levelname)s] [CID: %(correlation_id)s] "
            "[%(name)s:%(funcName)s:%(lineno)d] - %(message)s"
        )
        
        formatter = logging.Formatter(log_format)
        return formatter.format(record)


def setup_logging(log_level: str = "INFO") -> CorrelationIdFilter:
    """
    Configure structured logging for the application.
    
    Returns:
        CorrelationIdFilter: Filter instance for setting correlation IDs
    """
    # Create correlation ID filter
    correlation_filter = CorrelationIdFilter()
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Set formatter
    console_handler.setFormatter(StructuredFormatter())
    
    # Add filter
    console_handler.addFilter(correlation_filter)
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    return correlation_filter


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(name)
