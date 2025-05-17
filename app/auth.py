import secrets
from typing import Optional
from passlib.context import CryptContext
from fastapi import HTTPException, Header
from redis import asyncio as redis
from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def get_redis():
    return redis.from_url(str(settings.redis_url), decode_responses=False)

async def hash_password(password: str) -> str:
    return pwd_context.hash(password)

async def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

async def create_token() -> str:
    return secrets.token_hex(32)

async def register_user(username: str, password: str):
    rds = await get_redis()
    key = f"user:{username}:data"
    if await rds.exists(key):
        raise HTTPException(status_code=400, detail="user exists")
    hashed = await hash_password(password)
    token = await create_token()
    await rds.hset(key, mapping={"password": hashed, "token": token})
    return token

async def login_user(username: str, password: str) -> str:
    rds = await get_redis()
    key = f"user:{username}:data"
    data = await rds.hgetall(key)
    if not data:
        raise HTTPException(status_code=400, detail="invalid credentials")
    hashed = data.get(b"password")
    if hashed is None or not await verify_password(password, hashed.decode()):
        raise HTTPException(status_code=400, detail="invalid credentials")
    token = await create_token()
    await rds.hset(key, "token", token)
    return token

async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing token")
    token = authorization.split()[1]
    rds = await get_redis()
    keys = await rds.keys("user:*:data")
    for key in keys:
        val = await rds.hget(key, "token")
        if val and val.decode() == token:
            return key.split(":")[1]
    raise HTTPException(status_code=401, detail="invalid token")