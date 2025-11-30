# pinecone_manager.py
from pinecone import Pinecone, ServerlessSpec
from config import settings

class PineconeManager:
    def __init__(self):
        self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index_name = settings.PINECONE_INDEX_NAME
        self.index = self._initialize_index()

    def _initialize_index(self):
        """인덱스가 없으면 생성하고, 연결된 인덱스 객체를 반환합니다."""
        existing_indexes = self.pc.list_indexes().names()
        
        if self.index_name not in existing_indexes:
            print(f"Index '{self.index_name}' not found. Creating...")
            self.pc.create_index(
                name=self.index_name,
                dimension=settings.PINECONE_DIMENSION,
                metric=settings.PINECONE_METRIC,
                spec=ServerlessSpec(
                    cloud=settings.PINECONE_CLOUD,
                    region=settings.PINECONE_REGION
                )
            )
        return self.pc.Index(self.index_name)

    def upsert_vector(self, vector_id: str, vector: list, metadata: dict):
        """벡터와 메타데이터를 저장합니다."""
        try:
            self.index.upsert([
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": metadata
                }
            ])
            return True
        except Exception as e:
            print(f"Error upserting vector: {e}")
            raise e

    def fetch_vector(self, vector_id: str):
        """ID로 벡터 정보를 조회합니다."""
        return self.index.fetch(ids=[vector_id])

    def query_vector(self, vector: list, top_k: int = 5, include_metadata: bool = True):
        """벡터로 유사한 항목을 검색합니다."""
        return self.index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=include_metadata
        )

    def delete_vector(self, vector_id: str):
        """ID로 벡터를 삭제합니다."""
        self.index.delete(ids=[vector_id])

    def delete_all_vectors(self):
        """모든 벡터를 삭제합니다."""
        self.index.delete(delete_all=True)

# 싱글톤처럼 사용하기 위해 인스턴스 생성
pinecone_db = PineconeManager()