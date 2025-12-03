"""
로깅 설정
"""
import logging
import sys


def setup_logging():
    """로깅 설정 초기화"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 로거 가져오기
    logger = logging.getLogger("crud-service")
    logger.setLevel(logging.INFO)
    
    return logger


logger = setup_logging()
