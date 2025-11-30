
import os
from dotenv import load_dotenv

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(dotenv_path=env_path)

class Config:
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME = "images"
    PINECONE_DIMENSION = 768  # KoCLIP dimension
    PINECONE_METRIC = "cosine"
    PINECONE_CLOUD = "aws"
    PINECONE_REGION = "us-east-1"

settings = Config()