"""
Enhanced tagging service with database integration
"""
from typing import List, Tuple, Optional
import os
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
        min_score: Optional[float] = None
    ):
        self.runner = MobileNetV3OnnxRunner(model_path, input_size, mean, std, apply_softmax)
        self.labels = labels
        # 태깅 임계값 (환경변수 TAGGING_MIN_SCORE 우선)
        try:
            env_min = os.getenv("TAGGING_MIN_SCORE")
            self.min_score = float(env_min) if env_min is not None else (min_score if min_score is not None else 0.5)
        except ValueError:
            self.min_score = min_score if min_score is not None else 0.5
    
    def predict_pil(self, img: Image.Image, top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        """PIL 이미지로부터 태그 예측 후 임계값으로 필터링"""
        probs = self.runner.predict(img)
        # 점수 내림차순 정렬 인덱스
        sorted_idx = np.argsort(-probs)
        results: List[Tuple[str, float]] = []
        for i in sorted_idx:
            score = float(probs[i])
            if score < self.min_score:
                # 임계값 미만은 제외
                continue
            label = self.labels[i] if i < len(self.labels) else f"class_{i}"
            results.append((label, score))
        return results
    
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
            # 파일 경로 검증
            if not task.file_path:
                logger.error(f"No file_path provided for data_id: {task.data_id}")
                raise ValueError(f"No file_path for data_id: {task.data_id}")
            
            # 1. 이미지 로드
            logger.info(f"Loading image from path: {task.file_path}")
            logger.info(f"File exists: {os.path.exists(task.file_path) if isinstance(task.file_path, str) else 'N/A'}")
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
