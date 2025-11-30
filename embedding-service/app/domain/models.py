"""
Domain models for Embedding Service.
Defines the core data structures used across the application.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Request model for image search."""
    query: str = Field(..., description="Search query text")
    top_k: int = Field(default=5, ge=1, le=100, description="Number of results to return")


class SearchResult(BaseModel):
    """Individual search result."""
    score: float = Field(..., description="Similarity score (0-1)")
    uuid: str = Field(..., description="Image UUID")
    file_path: Optional[str] = Field(None, description="File path in shared storage")
    filename: Optional[str] = Field(None, description="Original filename")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class SearchResponse(BaseModel):
    """Response model for search endpoint."""
    results: List[SearchResult] = Field(default_factory=list)
    query: str = Field(..., description="Original query")
    total_results: int = Field(..., description="Number of results returned")


class DeleteRequest(BaseModel):
    """Request model for deleting an image vector."""
    user_id: str = Field(..., description="User ID for permission check")
    image_uuid: str = Field(..., description="Image UUID to delete")


class DeleteResponse(BaseModel):
    """Response model for delete endpoint."""
    message: str = Field(..., description="Deletion result message")
    uuid: str = Field(..., description="Deleted image UUID")


class EmbeddingTask(BaseModel):
    """Task model for processing image embeddings from queue."""
    uuid: str = Field(..., description="Image UUID")
    file_path: str = Field(..., description="Path to image file in shared storage")
    user_id: str = Field(..., description="User ID who owns the image")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracing")


class VectorData(BaseModel):
    """Vector data with metadata."""
    id: str = Field(..., description="Vector ID (image UUID)")
    values: List[float] = Field(..., description="Vector values")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Vector metadata")


class VectorSearchResult(BaseModel):
    """Result from vector database query."""
    matches: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = Field(0, description="Total number of matches")
