"""
Search and embedding API routes.
Provides endpoints for image search and vector operations.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends

from app.core.logging import get_logger
from app.domain.models import (
    SearchRequest, SearchResponse,
    DeleteRequest, DeleteResponse
)
from app.services.embedding_service import EmbeddingService
from app.api.dependencies import get_embedding_service

logger = get_logger(__name__)
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_images(
    request: SearchRequest,
    x_correlation_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Search for similar images using text query.
    
    Args:
        request: Search request with query text and top_k
        x_correlation_id: Optional correlation ID for request tracing
        embedding_service: Injected embedding service
        
    Returns:
        SearchResponse with matching images sorted by similarity
        
    Example:
        ```
        POST /search
        {
            "query": "고양이",
            "top_k": 5
        }
        ```
    """
    try:
        logger.info(f"Search request: query='{request.query}', top_k={request.top_k}")
        
        # Set correlation ID for logging
        if x_correlation_id:
            from app.core.logging import setup_logging
            from app.core.config import settings
            correlation_filter = setup_logging(settings.LOG_LEVEL)
            correlation_filter.set_correlation_id(x_correlation_id)
        
        # Execute search
        response = await embedding_service.search_images(
            request=request,
            correlation_id=x_correlation_id,
            user_id=x_user_id
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.delete("/images", response_model=DeleteResponse)
async def delete_image(
    request: DeleteRequest,
    x_correlation_id: Optional[str] = Header(None),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Delete an image vector with ownership verification.
    
    Args:
        request: Delete request with user_id and image_uuid
        x_correlation_id: Optional correlation ID for request tracing
        embedding_service: Injected embedding service
        
    Returns:
        DeleteResponse confirming deletion
        
    Raises:
        404: Image not found
        403: Permission denied (not owner)
        
    Example:
        ```
        DELETE /images
        {
            "user_id": "user_123",
            "image_uuid": "img_abc"
        }
        ```
    """
    try:
        logger.info(f"Delete request: uuid={request.image_uuid}, user={request.user_id}")
        
        # Set correlation ID for logging
        if x_correlation_id:
            from app.core.logging import setup_logging
            from app.core.config import settings
            correlation_filter = setup_logging(settings.LOG_LEVEL)
            correlation_filter.set_correlation_id(x_correlation_id)
        
        # Execute deletion
        response = await embedding_service.delete_image(
            request=request,
            correlation_id=x_correlation_id
        )
        
        return response
        
    except ValueError as e:
        logger.warning(f"Image not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        logger.warning(f"Permission denied: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {str(e)}"
        )


@router.delete("/admin/delete-all")
async def delete_all_images(
    x_correlation_id: Optional[str] = Header(None),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Delete all vectors (admin operation).
    
    WARNING: This will delete ALL embeddings in the database.
    Use only for testing or maintenance.
    
    Args:
        x_correlation_id: Optional correlation ID for request tracing
        embedding_service: Injected embedding service
        
    Returns:
        Confirmation message
    """
    try:
        logger.warning("Admin delete-all request received")
        
        # Set correlation ID for logging
        if x_correlation_id:
            from app.core.logging import setup_logging
            from app.core.config import settings
            correlation_filter = setup_logging(settings.LOG_LEVEL)
            correlation_filter.set_correlation_id(x_correlation_id)
        
        # Execute deletion
        result = await embedding_service.delete_all_images(
            correlation_id=x_correlation_id
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Delete all failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Delete all failed: {str(e)}"
        )
