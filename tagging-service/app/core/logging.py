"""
Logging configuration
"""
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """로거 인스턴스 생성"""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # 콘솔 핸들러
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        
        # 포맷터
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
    
    return logger


# 기본 로거
logger = get_logger(__name__)
