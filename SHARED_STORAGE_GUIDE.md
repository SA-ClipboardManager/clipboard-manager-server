# 공유 이미지 저장소 가이드

## 개요

모든 마이크로서비스(login-service 제외)가 동일한 이미지 파일에 접근할 수 있도록 Docker 공유 볼륨을 구성했습니다.

## 아키텍처

### 공유 볼륨 구조

```
shared_images/                    # Docker Volume
├── uploads/
│   ├── original/                # 원본 이미지
│   │   ├── {id}.png
│   │   ├── {id}.jpg
│   │   └── ...
│   └── thumbnail/               # 썸네일 이미지
│       ├── {id}_thumb.jpg
│       └── ...
└── temp/                        # 임시 파일 (선택사항)
```

### 서비스별 마운트 경로

모든 서비스는 동일한 볼륨을 `/app/shared_images`에 마운트합니다:

| 서비스                   | 컨테이너 내부 경로   | 용도                              |
| ------------------------ | -------------------- | --------------------------------- |
| **crud-service**         | `/app/shared_images` | 이미지 업로드 및 저장 (주 작성자) |
| **embedding-service**    | `/app/shared_images` | 이미지 임베딩 생성 (읽기)         |
| **tagging-service**      | `/app/shared_images` | 이미지 태그 분석 (읽기)           |
| **monitoring-service**   | `/app/shared_images` | 이미지 메트릭 수집 (읽기)         |
| **notification-service** | `/app/shared_images` | 이미지 알림 전송 (읽기)           |
| **login-service**        | -                    | 공유 볼륨 미사용                  |

## Docker Compose 설정

### volumes 정의

```yaml
volumes:
  shared_images:
    driver: local
```

### 서비스별 볼륨 마운트

```yaml
services:
  crud-service:
    volumes:
      - shared_images:/app/shared_images

  embedding-service:
    volumes:
      - shared_images:/app/shared_images

  tagging-service:
    volumes:
      - shared_images:/app/shared_images

  monitoring-service:
    volumes:
      - shared_images:/app/shared_images

  notification-service:
    volumes:
      - shared_images:/app/shared_images
```

## 서비스별 사용 예시

### 1. CRUD Service (이미지 저장)

```python
# crud-service/app/main.py
SHARED_IMAGE_DIR = "/app/shared_images"
UPLOAD_DIR = os.path.join(SHARED_IMAGE_DIR, "uploads")
original_dir = os.path.join(UPLOAD_DIR, "original")
thumbnail_dir = os.path.join(UPLOAD_DIR, "thumbnail")

# 이미지 저장
file_path = os.path.join(original_dir, f"{id}.{format}")
async with aiofiles.open(file_path, 'wb') as f:
    await f.write(content)

# 썸네일 저장
thumb_path = os.path.join(thumbnail_dir, f"{id}_thumb.jpg")
img.save(thumb_path, "JPEG", quality=85)
```

### 2. Embedding Service (이미지 읽기)

```python
# embedding-service/app/main.py
import os
from PIL import Image

SHARED_IMAGE_DIR = "/app/shared_images"

async def process_image(image_id: str, format: str):
    # 공유 볼륨에서 이미지 읽기
    image_path = os.path.join(
        SHARED_IMAGE_DIR,
        "uploads",
        "original",
        f"{image_id}.{format}"
    )

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_id}")

    # 이미지 처리
    img = Image.open(image_path)
    # ... 임베딩 생성
```

### 3. Tagging Service (이미지 분석)

```python
# tagging-service/app/main.py
import os
from PIL import Image

SHARED_IMAGE_DIR = "/app/shared_images"

async def analyze_image(image_id: str, format: str):
    # 공유 볼륨에서 이미지 읽기
    image_path = os.path.join(
        SHARED_IMAGE_DIR,
        "uploads",
        "original",
        f"{image_id}.{format}"
    )

    img = Image.open(image_path)
    # ... 태그 분석
```

### 4. Monitoring Service (메트릭 수집)

```python
# monitoring-service/app/main.py
import os

SHARED_IMAGE_DIR = "/app/shared_images"

async def collect_metrics():
    upload_dir = os.path.join(SHARED_IMAGE_DIR, "uploads", "original")

    # 파일 개수 및 크기 통계
    file_count = len(os.listdir(upload_dir))
    total_size = sum(
        os.path.getsize(os.path.join(upload_dir, f))
        for f in os.listdir(upload_dir)
    )

    # ... 메트릭 저장
```

## 이벤트 기반 통신 흐름

### 이미지 업로드 시나리오

```
1. Client → CRUD Service: 이미지 업로드
   ├─ CRUD: /app/shared_images/uploads/original/{id}.png 저장
   ├─ CRUD: /app/shared_images/uploads/thumbnail/{id}_thumb.jpg 생성
   └─ CRUD: RabbitMQ에 "image_created" 이벤트 발행

2. RabbitMQ → Embedding Service: "image_created" 이벤트 수신
   ├─ /app/shared_images/uploads/original/{id}.png 읽기
   └─ 임베딩 벡터 생성 및 저장

3. RabbitMQ → Tagging Service: "image_created" 이벤트 수신
   ├─ /app/shared_images/uploads/original/{id}.png 읽기
   └─ 자동 태그 생성

4. RabbitMQ → Notification Service: "image_created" 이벤트 수신
   └─ WebSocket으로 클라이언트에 알림 전송
```

## 베스트 프랙티스

### 1. 파일 명명 규칙

- **원본 이미지**: `{uuid}.{format}` (예: `a1b2c3d4-e5f6.png`)
- **썸네일**: `{uuid}_thumb.jpg` (예: `a1b2c3d4-e5f6_thumb.jpg`)
- **임시 파일**: `temp_{uuid}_{timestamp}.{format}`

### 2. 파일 접근 권한

```python
# 읽기 전 파일 존재 확인
if not os.path.exists(image_path):
    logger.error(f"Image not found: {image_id}")
    raise FileNotFoundError()

# 쓰기 전 디렉토리 생성
os.makedirs(upload_dir, exist_ok=True)
```

### 3. 에러 처리

```python
try:
    img = Image.open(image_path)
except FileNotFoundError:
    logger.error(f"Image file missing: {image_id}")
    # 재시도 로직 또는 에러 알림
except Exception as e:
    logger.error(f"Failed to process image: {e}")
```

### 4. 동시성 제어

- **읽기**: 여러 서비스가 동시에 읽을 수 있음 (안전)
- **쓰기**: CRUD 서비스만 쓰기 권한 (단일 작성자 패턴)
- **삭제**: CRUD 서비스만 삭제 권한

### 5. 파일 정리

```python
# 삭제된 데이터의 파일 정리
def cleanup_image_files(image_id: str, format: str):
    original_path = os.path.join(original_dir, f"{image_id}.{format}")
    thumb_path = os.path.join(thumbnail_dir, f"{image_id}_thumb.jpg")

    for path in [original_path, thumb_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Deleted: {path}")
            except Exception as e:
                logger.error(f"Failed to delete {path}: {e}")
```

## 볼륨 관리

### 볼륨 확인

```bash
# 볼륨 목록 확인
docker volume ls

# 공유 볼륨 상세 정보
docker volume inspect clipboard-manager-server_shared_images
```

### 볼륨 백업

```bash
# 볼륨 백업
docker run --rm \
  -v clipboard-manager-server_shared_images:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/shared_images_backup.tar.gz -C /data .

# 볼륨 복원
docker run --rm \
  -v clipboard-manager-server_shared_images:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/shared_images_backup.tar.gz"
```

### 볼륨 정리

```bash
# 사용하지 않는 볼륨 삭제
docker volume prune

# 특정 볼륨 삭제 (주의!)
docker volume rm clipboard-manager-server_shared_images
```

## 성능 최적화

### 1. 캐싱 전략

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_image_path(image_id: str, format: str) -> str:
    return os.path.join(SHARED_IMAGE_DIR, "uploads", "original", f"{image_id}.{format}")
```

### 2. 비동기 I/O

```python
import aiofiles

async def read_image_async(image_path: str) -> bytes:
    async with aiofiles.open(image_path, 'rb') as f:
        return await f.read()
```

### 3. 스트리밍

```python
from fastapi.responses import FileResponse

@app.get("/images/{image_id}")
async def get_image(image_id: str):
    image_path = get_image_path(image_id, "png")
    return FileResponse(image_path, media_type="image/png")
```

## 모니터링

### 디스크 사용량 추적

```python
import shutil

def get_disk_usage():
    total, used, free = shutil.disk_usage(SHARED_IMAGE_DIR)
    return {
        "total_gb": total // (2**30),
        "used_gb": used // (2**30),
        "free_gb": free // (2**30),
        "usage_percent": (used / total) * 100
    }
```

### 파일 통계

```python
def get_file_statistics():
    stats = {
        "total_files": 0,
        "total_size_mb": 0,
        "by_format": {}
    }

    for filename in os.listdir(original_dir):
        file_path = os.path.join(original_dir, filename)
        size = os.path.getsize(file_path)
        ext = filename.split('.')[-1]

        stats["total_files"] += 1
        stats["total_size_mb"] += size / (1024 * 1024)
        stats["by_format"][ext] = stats["by_format"].get(ext, 0) + 1

    return stats
```

## 트러블슈팅

### 문제: 파일이 보이지 않음

```bash
# 컨테이너 내부에서 확인
docker exec -it crud-service ls -la /app/shared_images/uploads/original

# 볼륨 마운트 확인
docker inspect crud-service | grep -A 10 Mounts
```

### 문제: 권한 오류

```bash
# 컨테이너 내부에서 권한 확인
docker exec -it crud-service ls -la /app/shared_images

# 권한 수정 (필요시)
docker exec -it crud-service chmod -R 755 /app/shared_images
```

### 문제: 디스크 공간 부족

```bash
# 사용량 확인
docker exec -it crud-service df -h /app/shared_images

# 오래된 파일 정리 (30일 이상)
docker exec -it crud-service find /app/shared_images -type f -mtime +30 -delete
```

## 보안 고려사항

1. **읽기 전용 마운트**: 읽기만 필요한 서비스는 `:ro` 플래그 사용
2. **파일 검증**: 업로드된 파일의 MIME 타입 및 크기 검증
3. **경로 검증**: 디렉토리 탐색 공격 방지
4. **바이러스 스캔**: 대용량 서비스의 경우 ClamAV 등 통합

## 확장 계획

### 클라우드 스토리지 마이그레이션

향후 AWS S3, Azure Blob Storage 등으로 마이그레이션 시:

1. 추상화 레이어 구현 (Storage Interface)
2. 로컬/클라우드 하이브리드 운영
3. 점진적 마이그레이션 전략

```python
# 추상화 예시
class StorageBackend:
    async def save(self, path: str, data: bytes): ...
    async def read(self, path: str) -> bytes: ...
    async def delete(self, path: str): ...

class LocalStorage(StorageBackend):
    # 현재 로컬 볼륨 구현
    pass

class S3Storage(StorageBackend):
    # 클라우드 스토리지 구현
    pass
```
