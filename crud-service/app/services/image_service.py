"""
이미지 처리 서비스
"""
import os
import io
import asyncio
from typing import Tuple, Optional
from PIL import Image
import aiofiles

from ..domain.models import ImageMeta
from ..domain.repositories import IClipboardRepository, IImageMetaRepository
from ..infrastructure.message_broker import MessageBroker
from ..core.config import settings
from ..core.logging import logger


class ImageService:
    """이미지 처리 비즈니스 로직"""
    
    def __init__(
        self,
        clipboard_repo: IClipboardRepository,
        image_repo: IImageMetaRepository,
        message_broker: MessageBroker
    ):
        self.clipboard_repo = clipboard_repo
        self.image_repo = image_repo
        self.message_broker = message_broker
        
        # 디렉토리 생성
        os.makedirs(settings.original_dir, exist_ok=True)
        os.makedirs(settings.thumbnail_dir, exist_ok=True)
    
    async def upload_image(
        self,
        file_content: bytes,
        item_id: str,
        format: str,
        created_at: int,
        user_id: str,
        filename: Optional[str] = None
    ) -> dict:
        """이미지 업로드 및 처리"""
        # 이미 존재하는지 확인
        if await self.clipboard_repo.exists(item_id):
            return {"id": item_id, "status": "exists", "message": "Already exists"}
        
        # 파일 크기
        file_size = len(file_content)
        
        # 이미지 검증 및 메타데이터 추출
        try:
            loop = asyncio.get_running_loop()
            image = await loop.run_in_executor(
                None,
                lambda: Image.open(io.BytesIO(file_content))
            )
            width, height = image.size
        except Exception as e:
            logger.error(f"Invalid image file: {e}")
            raise ValueError("Invalid image file")
        
        # 파일명 생성
        ext = self._get_extension(filename, format)
        orig_name = f"{item_id}.{ext}"
        thumb_name = f"{item_id}_thumb.{ext}"
        
        # 파일 경로
        orig_path_fs = os.path.join(settings.original_dir, orig_name)
        thumb_path_fs = os.path.join(settings.thumbnail_dir, thumb_name)
        
        # URL 경로
        orig_url = f"/local/original/{orig_name}"
        thumb_url = f"/local/thumbnail/{thumb_name}"
        
        try:
            # 원본 이미지 저장
            async with aiofiles.open(orig_path_fs, 'wb') as f:
                await f.write(file_content)
            
            # 썸네일 생성 및 저장
            await self._create_thumbnail(image, thumb_path_fs)
            
            # DB에 저장 (트랜잭션은 상위 레이어에서 처리)
            from ..domain.models import ClipboardItem
            item = ClipboardItem(
                id=item_id,
                user_id=user_id,
                type="img",
                format=format,
                content=orig_url,
                created_at=created_at
            )
            await self.clipboard_repo.create(item)
            
            # 이미지 메타데이터 저장
            meta = ImageMeta(
                data_id=item_id,
                width=width,
                height=height,
                file_size=file_size,
                file_path=orig_url,
                thumbnail_path=thumb_url
            )
            await self.image_repo.create(meta)
            
            # 이벤트 발행: service.crud.item.saved.img
            await self.message_broker.publish_event("service.crud.item.saved.img", {
                "data_id": item_id,
                "user_id": user_id,
                "file_path": orig_path_fs,
                "thumbnail_path": thumb_path_fs,
                "created_at": created_at,
                "format": format,
                "width": width,
                "height": height,
                "file_size": file_size
            })
            
            return {
                "id": item_id,
                "status": "uploaded",
                "message": "Uploaded successfully"
            }
        
        except Exception as e:
            # 실패 시 파일 정리
            self._cleanup_files([orig_path_fs, thumb_path_fs])
            raise e
    
    async def upload_clipboard_image(
        self,
        file_content: bytes,
        item_id: str,
        format: str,
        created_at: int,
        user_id: str
    ) -> dict:
        """클립보드 이미지 업로드 (ISO 타임스탬프 처리 포함)"""
        from datetime import datetime
        
        # ISO 문자열을 Unix 타임스탬프로 변환
        if isinstance(created_at, str):
            created_ts = int(
                datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
            )
        else:
            created_ts = created_at
        
        # 이미지 메타데이터 추출
        loop = asyncio.get_running_loop()
        img = await loop.run_in_executor(
            None,
            lambda: Image.open(io.BytesIO(file_content))
        )
        width, height = img.size
        file_size = len(file_content)
        
        # 파일 저장
        ext = format.lower() if format else 'png'
        file_path = os.path.join(settings.original_dir, f"{item_id}.{ext}")
        thumb_path = os.path.join(settings.thumbnail_dir, f"{item_id}_thumb.jpg")
        
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        
        # 썸네일 생성
        await self._create_thumbnail(img, thumb_path, size=(200, 200))
        
        # URL 경로 생성
        file_url = f"/local/original/{item_id}.{ext}"
        thumb_url = f"/local/thumbnail/{item_id}_thumb.jpg"
        
        # 메타데이터 저장
        meta = ImageMeta(
            data_id=item_id,
            width=width,
            height=height,
            file_size=file_size,
            file_path=file_url,
            thumbnail_path=thumb_url
        )
        await self.image_repo.update(meta)
        
        # 이벤트 발행은 clipboard_service.create_item()에서 이미 처리됨
        
        return {"id": item_id, "status": "created"}
    
    async def _create_thumbnail(
        self,
        image: Image.Image,
        path: str,
        size: Tuple[int, int] = (256, 256)
    ):
        """썸네일 생성 (RGBA 이미지 처리 포함)"""
        loop = asyncio.get_running_loop()
        
        def save_thumb():
            thumb = image.copy()
            thumb.thumbnail(size)
            
            # RGBA 이미지인 경우 RGB로 변환
            if thumb.mode in ('RGBA', 'LA', 'P'):
                # 흰색 배경 생성
                background = Image.new('RGB', thumb.size, (255, 255, 255))
                if thumb.mode == 'P':
                    thumb = thumb.convert('RGBA')
                background.paste(thumb, mask=thumb.split()[-1] if thumb.mode in ('RGBA', 'LA') else None)
                thumb = background
            
            thumb.save(path, "JPEG", quality=85)
        
        await loop.run_in_executor(None, save_thumb)
    
    def _get_extension(self, filename: Optional[str], format: str) -> str:
        """파일 확장자 추출"""
        if filename and '.' in filename:
            return filename.split('.')[-1]
        return format or 'bin'
    
    def _cleanup_files(self, paths: list):
        """파일 정리"""
        for path in paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup file {path}: {e}")
    
    @staticmethod
    def delete_image_files(file_path: Optional[str], thumbnail_path: Optional[str]):
        """이미지 파일 삭제"""
        for path in [file_path, thumbnail_path]:
            if not path:
                continue
            
            # URL 경로를 파일시스템 경로로 변환
            if path.startswith("/local/original/"):
                fs_path = os.path.join(settings.original_dir, os.path.basename(path))
            elif path.startswith("/local/thumbnail/"):
                fs_path = os.path.join(settings.thumbnail_dir, os.path.basename(path))
            else:
                fs_path = path
            
            if os.path.exists(fs_path):
                try:
                    os.remove(fs_path)
                    logger.info(f"Deleted file: {fs_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {fs_path}: {e}")
