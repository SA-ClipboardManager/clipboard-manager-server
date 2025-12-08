"""
Correlation ID 유틸리티
요청 추적을 위한 고유 ID 생성 및 관리
"""
import uuid


def generate_correlation_id() -> str:
    """
    새로운 correlation ID 생성
    
    Returns:
        str: UUID v4 형식의 correlation ID
    """
    return str(uuid.uuid4())


def get_or_create_correlation_id(existing_id: str = None) -> str:
    """
    correlation ID 생성 또는 기존 ID 반환
    
    Args:
        existing_id: 기존 correlation ID (있으면 재사용)
    
    Returns:
        str: correlation ID
    """
    return existing_id if existing_id else generate_correlation_id()


# HTTP 헤더 이름 상수
CORRELATION_ID_HEADER = "X-Correlation-ID"
