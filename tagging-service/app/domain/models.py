"""
Domain models for tagging service
CCD-main의 tag/data_tag 테이블 구조 참조
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Tag:
    """태그 모델"""
    tag_id: str
    name: str
    source: str  # 'auto' or 'user'
    
    def __post_init__(self):
        if self.source not in ('auto', 'user'):
            raise ValueError(f"Invalid source: {self.source}. Must be 'auto' or 'user'")


@dataclass
class DataTag:
    """데이터-태그 연결 모델"""
    data_id: str
    tag_id: str


@dataclass
class TaggingTask:
    """태깅 작업 모델"""
    data_id: str
    user_id: str
    file_path: str
    thumbnail_path: Optional[str] = None
    created_at: Optional[int] = None
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
