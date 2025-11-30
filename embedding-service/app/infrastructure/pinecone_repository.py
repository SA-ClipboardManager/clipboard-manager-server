"""
Pinecone vector database repository implementation.
Handles all vector storage and retrieval operations.
"""

import asyncio
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.repositories import IVectorRepository
from app.domain.models import VectorData, VectorSearchResult

logger = get_logger(__name__)


class PineconeRepository(IVectorRepository):
    """Pinecone implementation of vector repository."""
    
    def __init__(self):
        """Initialize Pinecone client and index."""
        self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index_name = settings.PINECONE_INDEX_NAME
        self._index = None
        logger.info(f"Initialized PineconeRepository with index: {self.index_name}")
    
    async def _get_index(self):
        """Get or create Pinecone index (lazy initialization)."""
        if self._index is None:
            await self._initialize_index()
        return self._index
    
    async def _initialize_index(self):
        """Initialize or create Pinecone index."""
        try:
            # Run blocking Pinecone operations in thread pool
            loop = asyncio.get_event_loop()
            existing_indexes = await loop.run_in_executor(
                None,
                lambda: self.pc.list_indexes().names()
            )
            
            if self.index_name not in existing_indexes:
                logger.info(f"Index '{self.index_name}' not found. Creating...")
                await loop.run_in_executor(
                    None,
                    lambda: self.pc.create_index(
                        name=self.index_name,
                        dimension=settings.PINECONE_DIMENSION,
                        metric=settings.PINECONE_METRIC,
                        spec=ServerlessSpec(
                            cloud=settings.PINECONE_CLOUD,
                            region=settings.PINECONE_REGION
                        )
                    )
                )
                logger.info(f"Index '{self.index_name}' created successfully")
            
            self._index = self.pc.Index(self.index_name)
            logger.info(f"Connected to Pinecone index: {self.index_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone index: {e}")
            raise
    
    async def upsert_vector(
        self,
        vector_id: str,
        vector: List[float],
        metadata: Dict[str, Any]
    ) -> bool:
        """Insert or update a vector in Pinecone."""
        try:
            index = await self._get_index()
            
            # Run upsert in thread pool (Pinecone SDK is synchronous)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: index.upsert([
                    {
                        "id": vector_id,
                        "values": vector,
                        "metadata": metadata
                    }
                ])
            )
            
            logger.info(f"Successfully upserted vector: {vector_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert vector {vector_id}: {e}")
            raise
    
    async def fetch_vector(self, vector_id: str) -> Optional[VectorData]:
        """Fetch a vector by ID from Pinecone."""
        try:
            index = await self._get_index()
            
            # Run fetch in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: index.fetch(ids=[vector_id])
            )
            
            if vector_id not in result.vectors:
                logger.warning(f"Vector not found: {vector_id}")
                return None
            
            vector_obj = result.vectors[vector_id]
            
            return VectorData(
                id=vector_id,
                values=vector_obj.values,
                metadata=vector_obj.metadata or {}
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch vector {vector_id}: {e}")
            raise
    
    async def query_vectors(
        self,
        vector: List[float],
        top_k: int = 5,
        include_metadata: bool = True
    ) -> VectorSearchResult:
        """Query similar vectors from Pinecone."""
        try:
            index = await self._get_index()
            
            # Run query in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: index.query(
                    vector=vector,
                    top_k=top_k,
                    include_metadata=include_metadata
                )
            )
            
            matches = []
            for match in result.get('matches', []):
                matches.append({
                    'id': match.get('id'),
                    'score': match.get('score'),
                    'metadata': match.get('metadata', {})
                })
            
            logger.info(f"Query returned {len(matches)} matches")
            
            return VectorSearchResult(
                matches=matches,
                total=len(matches)
            )
            
        except Exception as e:
            logger.error(f"Failed to query vectors: {e}")
            raise
    
    async def delete_vector(self, vector_id: str) -> bool:
        """Delete a vector by ID from Pinecone."""
        try:
            index = await self._get_index()
            
            # Run delete in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: index.delete(ids=[vector_id])
            )
            
            logger.info(f"Successfully deleted vector: {vector_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete vector {vector_id}: {e}")
            raise
    
    async def delete_all_vectors(self) -> bool:
        """Delete all vectors from Pinecone (admin operation)."""
        try:
            index = await self._get_index()
            
            # Run delete_all in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: index.delete(delete_all=True)
            )
            
            logger.warning("All vectors deleted from Pinecone")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete all vectors: {e}")
            raise
