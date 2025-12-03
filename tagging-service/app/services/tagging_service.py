"""
Enhanced tagging service with database integration
"""
from typing import List, Tuple, Optional
import numpy as np
from PIL import Image

from app.infrastructure.mobilenetv3_onnx import MobileNetV3OnnxRunner
from app.domain.models import Tag, DataTag, TaggingTask
from app.domain.repositories import ITagRepository, IDataTagRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class TaggingService:
    """태깅 서비스 (이미지 태깅 + DB 저장)"""
    
    def __init__(
        self,
        model_path: str,
        labels: List[str],
        input_size: int = 224,
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225),
        apply_softmax=True,
        default_top_k: int = 5
    ):
        self.runner = MobileNetV3OnnxRunner(model_path, input_size, mean, std, apply_softmax)
        self.labels = labels
        self.default_top_k = default_top_k
    
    def predict_pil(self, img: Image.Image, top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        """PIL 이미지로부터 태그 예측 (API 용)"""
        probs = self.runner.predict(img)
        k = top_k or self.default_top_k
        k = min(k, probs.shape[-1])
        idx = np.argsort(-probs)[:k]
        return [(self.labels[i] if i < len(self.labels) else f"class_{i}", float(probs[i])) for i in idx]
    
    async def process_and_save_tags(
        self,
        task: TaggingTask,
        tag_repo: ITagRepository,
        data_tag_repo: IDataTagRepository
    ) -> List[Tuple[str, float]]:
        """
        이미지 태깅 및 DB 저장
        
        Args:
            task: 태깅 작업 정보
            tag_repo: 태그 저장소
            data_tag_repo: 데이터-태그 연결 저장소
            
        Returns:
            태그 리스트 [(label, score), ...]
        """
        try:
            # 1. 이미지 로드
            logger.info(f"Loading image: {task.file_path}")
            img = Image.open(task.file_path).convert("RGB")
            
            # 2. 태그 예측
            logger.info(f"Predicting tags for data_id: {task.data_id}")
            tags = self.predict_pil(img)
            
            # 3. DB에 태그 저장
            logger.info(f"Saving tags to database: {tags}")
            for label, score in tags:
                # 태그 조회 또는 생성 (source='auto')
                tag = await tag_repo.get_or_create(name=label, source='auto')
                
                # 데이터-태그 연결 생성
                data_tag = DataTag(
                    data_id=task.data_id,
                    tag_id=tag.tag_id
                )
                
                # 중복 확인 후 저장
                if not await data_tag_repo.exists(task.data_id, tag.tag_id):
                    await data_tag_repo.create(data_tag)
                    logger.info(f"Saved tag '{label}' (score: {score:.3f}) for data_id: {task.data_id}")
                else:
                    logger.info(f"Tag '{label}' already exists for data_id: {task.data_id}")
            
            logger.info(f"Successfully tagged data_id: {task.data_id} with {len(tags)} tags")
            return tags
            
        except FileNotFoundError:
            logger.error(f"Image file not found: {task.file_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to process and save tags for data_id {task.data_id}: {e}", exc_info=True)
            raise
