import secrets
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from redis import asyncio as redis
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP bearer scheme for authentication in Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)

async def get_redis():
    logger.debug("Connecting to redis")
    return redis.from_url(str(settings.redis_url), decode_responses=False)

async def hash_password(password: str) -> str:
    return pwd_context.hash(password)

async def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

async def create_token() -> str:
    return secrets.token_hex(32)

async def register_user(username: str, password: str, company_id: str):
    logger.info("Registering user %s", username)
    rds = await get_redis()
    key = f"user:{username}:data"
    if await rds.exists(key):
        raise HTTPException(status_code=400, detail="user exists")
    hashed = await hash_password(password)
    token = await create_token()
    await rds.hset(
        key,
        mapping={"password": hashed, "token": token, "company_id": company_id},
    )
    await rds.sadd(f"company:{company_id}:users", username)
    await rds.set(f"token:{token}", f"{username}:{company_id}", ex=settings.token_ttl)
    return token

async def login_user(username: str, password: str) -> str:
    logger.info("Login attempt for %s", username)
    rds = await get_redis()
    key = f"user:{username}:data"
    data = await rds.hgetall(key)
    if not data:
        raise HTTPException(status_code=400, detail="invalid credentials")
    hashed = data.get(b"password")
    if hashed is None or not await verify_password(password, hashed.decode()):
        raise HTTPException(status_code=400, detail="invalid credentials")
    token = await create_token()
    company_id = data.get(b"company_id")
    if company_id is None:
        raise HTTPException(status_code=400, detail="invalid credentials")
    company_id = company_id.decode()
    old_token = data.get(b"token")
    if old_token:
        await rds.delete(f"token:{old_token.decode()}")
    await rds.hset(key, "token", token)
    await rds.set(
        f"token:{token}", f"{username}:{company_id}", ex=settings.token_ttl
    )
    return token

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> tuple[str, str]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing token")
    token = credentials.credentials
    rds = await get_redis()
    pair = await rds.get(f"token:{token}")
    if not pair:
        logger.warning("Invalid token access")
        raise HTTPException(status_code=401, detail="invalid token")
    if isinstance(pair, bytes):
        pair = pair.decode()
    if ":" not in pair:
        # legacy token without company info
        username = pair
        company_id = await rds.hget(f"user:{username}:data", "company_id")
        if isinstance(company_id, bytes):
            company_id = company_id.decode()
    else:
        username, company_id = pair.split(":", 1)
    stored = await rds.hget(f"user:{username}:data", "company_id")
    if isinstance(stored, bytes):
        stored = stored.decode()
    if stored != company_id:
        logger.warning("Token company mismatch for %s", username)
        raise HTTPException(status_code=401, detail="invalid token")
    return username, company_id

