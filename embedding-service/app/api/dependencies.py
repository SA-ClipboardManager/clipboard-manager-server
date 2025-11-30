"""
Dependency injection configuration for FastAPI.
Provides singleton instances of services and repositories.
"""

from functools import lru_cache

from app.infrastructure.pinecone_repository import PineconeRepository
from app.infrastructure.koclip_embedder import KoCLIPEmbedder
from app.services.embedding_service import EmbeddingService
from app.domain.repositories import IVectorRepository, IEmbeddingModel


# Singleton instances
_vector_repository: IVectorRepository = None
_embedding_model: IEmbeddingModel = None
_embedding_service: EmbeddingService = None


def get_vector_repository() -> IVectorRepository:
    """Get singleton vector repository instance."""
    global _vector_repository
    if _vector_repository is None:
        _vector_repository = PineconeRepository()
    return _vector_repository


def get_embedding_model() -> IEmbeddingModel:
    """Get singleton embedding model instance."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = KoCLIPEmbedder()
    return _embedding_model


def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(
            vector_repository=get_vector_repository(),
            embedding_model=get_embedding_model()
        )
    return _embedding_service
