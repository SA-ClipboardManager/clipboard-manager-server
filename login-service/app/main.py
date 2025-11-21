import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Literal, Optional

import aiomysql
import bcrypt
import jwt
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings
from redis.asyncio import Redis

# --------------------------------------------------------------------------
# 1. 설정 및 로깅
# --------------------------------------------------------------------------
# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("login-service")

class Settings(BaseSettings):
    # DB 설정 (Docker Compose 서비스명 사용)
    db_host: str = "login-mysql-db"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = Field(..., alias="DB_PASSWORD")
    db_name: str = "login_db"

    # Redis 설정 (Rate Limiting 및 캐싱)
    redis_url: str = "redis://login-redis-cache:6379"

    # JWT 설정
    secret_key: str = Field(..., alias="SECRET_KEY")
    algorithm: Literal['HS256', 'HS384', 'HS512'] = 'HS256'
    access_token_expire_minutes: int = 1440  # 24시간
    refresh_token_expire_days: int = 7

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

settings = Settings()

# --------------------------------------------------------------------------
# 2. 데이터 모델 (Pydantic)
# --------------------------------------------------------------------------
class UserSignupRequest(BaseModel):
    user_id: str = Field(..., min_length=4, max_length=50)
    password: str = Field(..., min_length=8)

class UserLoginRequest(UserSignupRequest):
    pass

class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    user_id: str
    created_at: int

# --------------------------------------------------------------------------
# 3. 전역 상태 및 DB 초기화
# --------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.db_pool = None
        self.redis = None

app_state = AppState()
security = HTTPBearer(auto_error=False)

# 사용자 및 인증 관련 테이블만 생성
async def initialize_database():
    CREATE_TABLES = """
        CREATE TABLE IF NOT EXISTS user (
            user_id VARCHAR(255) PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            created_at INTEGER NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS refresh_token (
            jti VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked BOOLEAN NOT NULL DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
        );
    """
    async with app_state.db_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                for statement in CREATE_TABLES.strip().split(';'):
                    stmt = statement.strip()
                    if stmt:
                        await cursor.execute(stmt + ';')
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                logger.error(f"Database initialization failed: {str(e)}")
                raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # MySQL 연결 풀
        app_state.db_pool = await aiomysql.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            db=settings.db_name,
            minsize=5,
            maxsize=20,
            auth_plugin="mysql_native_password",
            charset="utf8mb4",
            autocommit=True,
        )

        # Redis 연결 및 RateLimiter 초기화
        app_state.redis = Redis.from_url(settings.redis_url)
        await FastAPILimiter.init(app_state.redis)

        # DB 초기화
        await initialize_database()
        
        logger.info("Login Service Started")
        yield

    except Exception as e:
        logger.critical(f"Startup failed: {str(e)}")
        raise
    finally:
        if app_state.db_pool:
            app_state.db_pool.close()
            await app_state.db_pool.wait_closed()
        if app_state.redis:
            await app_state.redis.close()

app = FastAPI(
    lifespan=lifespan, 
    root_path="/auth/v1"  
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# 4. 유틸리티 함수
# --------------------------------------------------------------------------
async def get_db():
    async with app_state.db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            yield conn, cursor

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": int(expire.timestamp()), "type": "access"},
        settings.secret_key,
        algorithm=settings.algorithm
    )

def create_refresh_token(user_id: str, jti: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": user_id, "exp": int(expire.timestamp()), "type": "refresh", "jti": jti},
        settings.secret_key,
        algorithm=settings.algorithm
    )

# 내부적으로 토큰을 파싱하는 함수 (Depends용)
async def get_current_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing credentials")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        if payload.get("type") != "access":
             raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        return {"user_id": payload["sub"]}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))

# --------------------------------------------------------------------------
# 5. API 엔드포인트
# --------------------------------------------------------------------------

@app.post("/api/v1/auth/signup")
async def signup(user: UserSignupRequest, db=Depends(get_db)):
    """회원가입"""
    conn, cursor = db
    try:
        await cursor.execute("SELECT user_id FROM user WHERE user_id = %s", (user.user_id,))
        if await cursor.fetchone():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"code": "USER_EXISTS", "detail": "이미 존재하는 사용자 ID입니다."}
            )

        hashed_pw = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
        await cursor.execute(
            "INSERT INTO user (user_id, password, created_at) VALUES (%s, %s, %s)",
            (user.user_id, hashed_pw, int(datetime.now(timezone.utc).timestamp()))
        )
        await conn.commit()
        return {"JoinResult": True}

    except Exception as e:
        await conn.rollback()
        logger.error("Signup failed", exc_info=e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="회원가입 처리 중 오류가 발생했습니다.")

@app.post("/api/v1/auth/login", dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def login(user: UserLoginRequest, db=Depends(get_db)):
    """로그인 및 토큰 발급"""
    conn, cursor = db
    try:
        await cursor.execute(
            "SELECT password FROM user WHERE user_id = %s",
            (user.user_id,)
        )
        result = await cursor.fetchone()

        if not result or not bcrypt.checkpw(user.password.encode(), result["password"].encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # 토큰 생성
        access_token = create_access_token(user.user_id)
        refresh_jti = str(uuid.uuid4())
        refresh_token = create_refresh_token(user.user_id, refresh_jti)

        # 리프레시 토큰 DB 저장
        expires_at = int((datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)).timestamp())
        await cursor.execute(
            "INSERT INTO refresh_token (jti, user_id, expires_at, revoked) VALUES (%s, %s, %s, %s)",
            (refresh_jti, user.user_id, expires_at, False)
        )
        await conn.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login failed", exc_info=e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed")

@app.post("/api/v1/auth/refresh", dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def refresh_token(request: RefreshTokenRequest, db=Depends(get_db)):
    """Access Token 재발급"""
    conn, cursor = db
    try:
        payload = jwt.decode(
            request.refresh_token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        
        user_id = payload.get("sub")
        jti = payload.get("jti")
        current_time = int(datetime.now(timezone.utc).timestamp())

        # DB 유효성 검사
        await cursor.execute(
            "SELECT jti FROM refresh_token WHERE jti = %s AND user_id = %s AND revoked = FALSE AND expires_at > %s",
            (jti, user_id, current_time)
        )
        if not await cursor.fetchone():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

        # 기존 토큰 폐기
        await cursor.execute("UPDATE refresh_token SET revoked = TRUE WHERE jti = %s", (jti,))

        # 새 토큰 발급
        new_access_token = create_access_token(user_id)
        new_refresh_jti = str(uuid.uuid4())
        new_refresh_token = create_refresh_token(user_id, new_refresh_jti)

        expires_at = int((datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)).timestamp())
        await cursor.execute(
            "INSERT INTO refresh_token (jti, user_id, expires_at, revoked) VALUES (%s, %s, %s, %s)",
            (new_refresh_jti, user_id, expires_at, False)
        )
        await conn.commit()

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    except Exception as e:
        await conn.rollback()
        logger.error("Refresh failed", exc_info=e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/api/v1/auth/verify", response_model=UserResponse)
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db=Depends(get_db)
):
    conn, cursor = db
    
    # [수정 1] try 블록 밖에서 먼저 체크 (여기서 401 터지면 바로 반환됨)
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No credentials")

    try:
        # 1. 토큰 검증
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        if payload.get("type") != "access":
             raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        
        user_id = payload.get("sub")

        await cursor.execute("SELECT user_id, created_at FROM user WHERE user_id = %s", (user_id,))
        user_info = await cursor.fetchone()

        if not user_info:
             raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        return user_info

    except HTTPException:
        raise 
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.get("/api/v1/users/me", response_model=UserResponse)
async def get_my_info(user: Dict = Depends(get_current_user_token), db=Depends(get_db)):
    """내 정보 조회"""
    conn, cursor = db
    await cursor.execute("SELECT user_id, created_at FROM user WHERE user_id = %s", (user["user_id"],))
    user_info = await cursor.fetchone()
    if not user_info:
        raise HTTPException(404, "User not found")
    return user_info

@app.get("/health")
def health_check():
    return {"status": "ok"}