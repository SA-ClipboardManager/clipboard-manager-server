"""
FastAPI application for Embedding Service.
Provides REST API for image search and vector operations.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api.search_routes import router as search_router


# Setup logging
correlation_filter = setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Manages startup and shutdown events.
    """
    # Startup
    logger.info("=" * 60)
    logger.info("Starting Embedding Service API")
    logger.info(f"Pinecone Index: {settings.PINECONE_INDEX_NAME}")
    logger.info(f"KoCLIP Model: {settings.KOCLIP_MODEL_REPO}")
    logger.info(f"Device: {settings.KOCLIP_DEVICE}")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Embedding Service API")


# Create FastAPI app
app = FastAPI(
    title="Embedding Service",
    description="Image embedding and semantic search service using KoCLIP",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(search_router, tags=["search"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "embedding-service",
        "status": "healthy",
        "version": "2.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "pinecone_index": settings.PINECONE_INDEX_NAME,
        "model": settings.KOCLIP_MODEL_REPO,
        "device": settings.KOCLIP_DEVICE
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True
    )
