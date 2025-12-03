"""
Embedding service - Business logic layer.
Handles image embedding generation, search, and deletion operations.
"""

import os
from typing import List, Optional

from app.core.logging import get_logger
from app.domain.repositories import IVectorRepository, IEmbeddingModel
from app.domain.models import (
    SearchRequest, SearchResponse, SearchResult,
    DeleteRequest, DeleteResponse,
    EmbeddingTask
)

logger = get_logger(__name__)


class EmbeddingService:
    """Service for managing image embeddings and vector operations."""
    
    def __init__(
        self,
        vector_repository: IVectorRepository,
        embedding_model: IEmbeddingModel
    ):
        """
        Initialize embedding service.
        
        Args:
            vector_repository: Repository for vector operations
            embedding_model: Model for generating embeddings
        """
        self.vector_repo = vector_repository
        self.embedding_model = embedding_model
        logger.info("EmbeddingService initialized")
    
    async def search_images(
        self,
        request: SearchRequest,
        correlation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> SearchResponse:
        """
        Search for similar images using text query.
        
        Args:
            request: Search request with query and top_k
            correlation_id: Optional correlation ID for tracing
            
        Returns:
            SearchResponse with matching images
        """
        try:
            logger.info(f"Searching for: '{request.query}' (top_k={request.top_k})")
            
            # 1. Encode text query to vector
            query_vector = await self.embedding_model.encode_text(request.query)
            logger.debug(f"Generated query vector (dim: {len(query_vector)})")
            
            # 2. Search in vector database
            # Apply user filter if provided
            metadata_filter = {"userid": user_id} if user_id else None
            search_result = await self.vector_repo.query_vectors(
                vector=query_vector,
                top_k=request.top_k,
                include_metadata=True,
                filter=metadata_filter
            )
            
            # 3. Transform to response format
            results = []
            for match in search_result.matches:
                metadata = match.get('metadata', {})
                results.append(SearchResult(
                    score=match.get('score', 0.0),
                    uuid=match.get('id', ''),
                    file_path=metadata.get('path'),
                    filename=metadata.get('filename'),
                    metadata=metadata
                ))
            
            logger.info(f"Found {len(results)} matching images")
            
            return SearchResponse(
                results=results,
                query=request.query,
                total_results=len(results)
            )
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    async def delete_image(
        self,
        request: DeleteRequest,
        correlation_id: Optional[str] = None
    ) -> DeleteResponse:
        """
        Delete an image vector with ownership verification.
        
        Args:
            request: Delete request with user_id and image_uuid
            correlation_id: Optional correlation ID for tracing
            
        Returns:
            DeleteResponse confirming deletion
        """
        try:
            vector_data = await self.vector_repo.fetch_vector(request.image_uuid)
            
            if vector_data is None:
                logger.warning(f"Image not found: {request.image_uuid}")
                raise ValueError(f"Image {request.image_uuid} not found")
            
            # 2. Verify ownership
            stored_user_id = vector_data.metadata.get("userid")
            if stored_user_id != request.user_id:
                logger.warning(
                    f"Permission denied: user {request.user_id} "
                    f"tried to delete image owned by {stored_user_id}"
                )
                raise PermissionError("You don't have permission to delete this image")
            
            # 3. Delete vector
            await self.vector_repo.delete_vector(request.image_uuid)
            
            logger.info(f"Successfully deleted image: {request.image_uuid}")
            
            return DeleteResponse(
                message=f"Image {request.image_uuid} deleted successfully",
                uuid=request.image_uuid
            )
            
        except (ValueError, PermissionError):
            raise
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            raise
    
    async def delete_all_images(
        self,
        correlation_id: Optional[str] = None
    ) -> dict:
        """
        Delete all vectors (admin operation).
        
        Args:
            correlation_id: Optional correlation ID for tracing
            
        Returns:
            Confirmation message
        """
        try:
            logger.warning("Deleting ALL vectors (admin operation)")
            
            await self.vector_repo.delete_all_vectors()
            
            logger.info("All vectors deleted successfully")
            
            return {"message": "All vectors deleted"}
            
        except Exception as e:
            logger.error(f"Delete all failed: {e}")
            raise
    
    async def process_embedding_task(
        self,
        task: EmbeddingTask
    ):
        """
        Process an embedding task from the message queue.
        
        Args:
            task: Embedding task with image info
        """
        try:
            logger.info(
                f"Processing embedding task for image: {task.uuid} "
                f"(user: {task.user_id}, path: {task.file_path})"
            )
            
            # 1. Validate file exists
            if not os.path.exists(task.file_path):
                logger.error(f"File not found: {task.file_path}")
                raise FileNotFoundError(f"Image file not found: {task.file_path}")
            
            # 2. Generate embedding
            logger.debug(f"Generating embedding for {task.file_path}")
            vector = await self.embedding_model.encode_image(task.file_path)
            logger.debug(f"Generated vector (dim: {len(vector)})")
            
            # 3. Store in vector database
            metadata = {
                "userid": task.user_id,
                "filename": os.path.basename(task.file_path),
                "path": task.file_path
            }
            
            if task.correlation_id:
                metadata["correlation_id"] = task.correlation_id
            
            await self.vector_repo.upsert_vector(
                vector_id=task.uuid,
                vector=vector,
                metadata=metadata
            )
            
            logger.info(f"Successfully processed embedding for image: {task.uuid}")
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to process embedding task: {e}")
            raise
