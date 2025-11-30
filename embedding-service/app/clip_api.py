# clip_api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

# 우리가 분리했던 모듈 재사용 (아주 효율적이죠!)
from pinecone_manager import pinecone_db
from koclip_model import embedder

app = FastAPI()

# 요청 바디 정의
class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

class DeleteRequest(BaseModel):
    user_id: str
    image_uuid: str

# 1. 검색 API (클라이언트가 가장 많이 쓸 기능)
@app.post("/search")
async def search_images(req: SearchRequest):
    """
    텍스트("고양이")를 받아서 유사한 이미지를 찾아 반환
    """
    try:
        # 1-1. 텍스트를 벡터로 변환 (AI 모델 사용)
        query_vector = embedder.encode_text(req.query)
        
        # 1-2. Pinecone에서 유사한 벡터 검색 (DB 매니저 사용)
        # include_metadata=True여야 파일 경로를 알 수 있음
        search_result = pinecone_db.query_vector(
            vector=query_vector, 
            top_k=req.top_k, 
            include_metadata=True
        )
        
        # 1-3. 클라이언트가 보기 좋게 결과 가공
        results = []
        for match in search_result['matches']:
            results.append({
                "score": match['score'],          # 유사도 (0~1)
                "uuid": match['id'],              # 이미지 UUID
                "file_path": match['metadata'].get('path'), # 파일 경로
                "filename": match['metadata'].get('filename')
            })
            
        return {"results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. 삭제 API 
@app.delete("/images")
async def delete_image(req: DeleteRequest):
    try:
        # 2-1. 해당 UUID의 벡터 정보 조회
        fetch_result = pinecone_db.fetch_vector(req.image_uuid)
        vectors = fetch_result.vectors
        
        if req.image_uuid not in vectors:
            raise HTTPException(status_code=404, detail="Image not found")
            
        vector_data = vectors[req.image_uuid]
        
        # 2-2. 소유권 확인 (내 거만 지울 수 있게)
        stored_user_id = vector_data.metadata.get("userid")
        if stored_user_id != req.user_id:
            raise HTTPException(status_code=403, detail="Permission denied")
            
        # 2-3. 삭제 수행
        pinecone_db.delete_vector(req.image_uuid)
        
        return {"message": f"Image {req.image_uuid} deleted successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# (옵션) 전체 삭제 - 테스트용
@app.delete("/admin/delete-all")
async def delete_all():
    try:
        pinecone_db.delete_all_vectors()
        return {"message": "All vectors deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))