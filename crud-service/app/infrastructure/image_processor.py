"""
이미지 처리 기술 구현체
PIL 의존성을 격리하여 비즈니스 로직과 분리
"""
import io
import asyncio
from typing import Tuple, Optional
from dataclasses import dataclass
from PIL import Image


@dataclass
class ImageMetadata:
    """이미지 메타데이터"""
    width: int
    height: int
    file_size: int
    format: str


@dataclass
class ProcessedImage:
    """처리된 이미지 데이터"""
    image: Image.Image
    metadata: ImageMetadata


class ImageProcessor:
    """이미지 처리 프로세서"""
    
    async def validate_and_extract_metadata(
        self,
        file_content: bytes
    ) -> ProcessedImage:
        """
        이미지 검증 및 메타데이터 추출
        
        Args:
            file_content: 이미지 파일 바이트
            
        Returns:
            ProcessedImage: PIL Image 객체와 메타데이터
            
        Raises:
            ValueError: 유효하지 않은 이미지 파일
        """
        try:
            loop = asyncio.get_running_loop()
            image = await loop.run_in_executor(
                None,
                lambda: Image.open(io.BytesIO(file_content))
            )
            
            width, height = image.size
            file_size = len(file_content)
            format_name = image.format or 'UNKNOWN'
            
            metadata = ImageMetadata(
                width=width,
                height=height,
                file_size=file_size,
                format=format_name
            )
            
            return ProcessedImage(image=image, metadata=metadata)
            
        except Exception as e:
            raise ValueError(f"Invalid image file: {e}")
    
    async def create_thumbnail(
        self,
        image: Image.Image,
        output_path: str,
        size: Tuple[int, int] = (256, 256),
        quality: int = 85
    ) -> None:
        """
        썸네일 생성 및 저장
        
        Args:
            image: PIL Image 객체
            output_path: 저장 경로
            size: 썸네일 크기 (width, height)
            quality: JPEG 품질 (1-100)
        """
        loop = asyncio.get_running_loop()
        
        def _save_thumbnail():
            thumb = image.copy()
            thumb.thumbnail(size)
            
            # RGBA 이미지인 경우 RGB로 변환 (JPEG 호환)
            if thumb.mode in ('RGBA', 'LA', 'P'):
                # 흰색 배경 생성
                background = Image.new('RGB', thumb.size, (255, 255, 255))
                if thumb.mode == 'P':
                    thumb = thumb.convert('RGBA')
                
                # 알파 채널을 마스크로 사용하여 배경에 합성
                if thumb.mode in ('RGBA', 'LA'):
                    background.paste(thumb, mask=thumb.split()[-1])
                else:
                    background.paste(thumb)
                
                thumb = background
            
            thumb.save(output_path, "JPEG", quality=quality)
        
        await loop.run_in_executor(None, _save_thumbnail)
    
    @staticmethod
    def get_file_extension(filename: Optional[str], fallback_format: str) -> str:
        """
        파일 확장자 추출
        
        Args:
            filename: 파일명
            fallback_format: 기본 포맷
            
        Returns:
            str: 파일 확장자
        """
        if filename and '.' in filename:
            return filename.split('.')[-1].lower()
        return (fallback_format or 'bin').lower()
