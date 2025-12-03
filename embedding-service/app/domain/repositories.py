"""
Repository interfaces for Embedding Service.
Defines contracts for data access and external services.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from .models import VectorData, VectorSearchResult


class IVectorRepository(ABC):
    """Interface for vector database operations."""
    
    @abstractmethod
    async def upsert_vector(
        self,
        vector_id: str,
        vector: List[float],
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Insert or update a vector in the database.
        
        Args:
            vector_id: Unique identifier for the vector
            vector: Vector values
            metadata: Associated metadata
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def fetch_vector(self, vector_id: str) -> Optional[VectorData]:
        """
        Fetch a vector by ID.
        
        Args:
            vector_id: Vector identifier
            
        Returns:
            VectorData if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def query_vectors(
        self,
        vector: List[float],
        top_k: int = 5,
        include_metadata: bool = True
    ) -> VectorSearchResult:
        """
        Query similar vectors.
        
        Args:
            vector: Query vector
            top_k: Number of results to return
            include_metadata: Whether to include metadata
            
        Returns:
            VectorSearchResult with matches
        """
        pass
    
    @abstractmethod
    async def delete_vector(self, vector_id: str) -> bool:
        """
        Delete a vector by ID.
        
        Args:
            vector_id: Vector identifier
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def delete_all_vectors(self) -> bool:
        """
        Delete all vectors (admin operation).
        
        Returns:
            True if successful
        """
        pass


class IEmbeddingModel(ABC):
    """Interface for embedding generation model."""
    
    @abstractmethod
    async def encode_text(self, text: str) -> List[float]:
        """
        Encode text to vector.
        
        Args:
            text: Input text
            
        Returns:
            Vector representation
        """
        pass
    
    @abstractmethod
    async def encode_image(self, image_path: str) -> List[float]:
        """
        Encode image to vector.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Vector representation
        """
        pass


class IMessageConsumer(ABC):
    """Interface for message queue consumer."""
    
    @abstractmethod
    async def start(self):
        """Start consuming messages from the queue."""
        pass
    
    @abstractmethod
    async def stop(self):
        """Stop consuming messages."""
        pass
