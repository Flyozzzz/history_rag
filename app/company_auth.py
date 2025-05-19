import logging
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from redis import asyncio as redis

from app.config import get_settings
from app.models import CompanyAuthResponse, CompanyFlagsResponse, CompanyFlagsUpdate

logger = logging.getLogger(__name__)

settings = get_settings()

router = APIRouter()

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


async def register_company(
    name: str,
    password: str,
    idle_timeout: int = 0,
    enable_summary: bool = True,
    enable_facts: bool = True,
    enable_calendar: bool = True,
) -> str:
    logger.info("Registering company %s", name)
    rds = await get_redis()
    key = f"company:{name}:data"
    if await rds.exists(key):
        raise HTTPException(status_code=400, detail="company exists")
    hashed = await hash_password(password)
    token = await create_token()
    await rds.hset(
        key,
        mapping={
            "password": hashed,
            "token": token,
            "idle_timeout": idle_timeout,
            "enable_summary": int(enable_summary),
            "enable_facts": int(enable_facts),
            "enable_calendar": int(enable_calendar),
        },
    )
    await rds.set(f"company_token:{token}", name, ex=settings.token_ttl)
    return token


async def login_company(name: str, password: str) -> str:
    logger.info("Company login attempt for %s", name)
    rds = await get_redis()
    key = f"company:{name}:data"
    data = await rds.hgetall(key)
    if not data:
        raise HTTPException(status_code=400, detail="invalid credentials")
    hashed = data.get(b"password")
    if hashed is None or not await verify_password(password, hashed.decode()):
        raise HTTPException(status_code=400, detail="invalid credentials")
    token = await create_token()
    old_token = data.get(b"token")
    if old_token:
        await rds.delete(f"company_token:{old_token.decode()}")
    await rds.hset(key, "token", token)
    await rds.set(f"company_token:{token}", name, ex=settings.token_ttl)
    return token


async def rotate_company_key(name: str) -> str:
    """Generate a new token for the company and update Redis."""
    logger.info("Rotating token for %s", name)
    rds = await get_redis()
    key = f"company:{name}:data"
    data = await rds.hgetall(key)
    if not data:
        raise HTTPException(status_code=400, detail="invalid company")
    new_token = await create_token()
    old_token = data.get(b"token")
    if old_token:
        await rds.delete(f"company_token:{old_token.decode()}")
    await rds.hset(key, "token", new_token)
    await rds.set(f"company_token:{new_token}", name, ex=settings.token_ttl)
    return new_token


async def get_current_company(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_cookie: str | None = Cookie(default=None, alias="company_token"),
) -> str:
    token = credentials.credentials if credentials else token_cookie
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    rds = await get_redis()
    name = await rds.get(f"company_token:{token}")
    if not name:
        logger.warning("Invalid company token access")
        raise HTTPException(status_code=401, detail="invalid token")
    if isinstance(name, bytes):
        name = name.decode()
    return name


@router.post("/company/rotate_key", response_model=CompanyAuthResponse)
async def rotate_key_endpoint(
    company: str = Depends(get_current_company),
) -> dict[str, str]:
    """Endpoint to rotate a company's access token."""
    token = await rotate_company_key(company)
    return {"name": company, "token": token}


async def update_company_flags(name: str, flags: CompanyFlagsUpdate) -> dict[str, bool]:
    rds = await get_redis()
    key = f"company:{name}:data"
    mapping = {}
    if flags.enable_summary is not None:
        mapping["enable_summary"] = int(flags.enable_summary)
    if flags.enable_facts is not None:
        mapping["enable_facts"] = int(flags.enable_facts)
    if flags.enable_calendar is not None:
        mapping["enable_calendar"] = int(flags.enable_calendar)
    if mapping:
        await rds.hset(key, mapping=mapping)
    data = await rds.hgetall(key)
    return {
        "enable_summary": bool(int(data.get(b"enable_summary", b"1"))),
        "enable_facts": bool(int(data.get(b"enable_facts", b"1"))),
        "enable_calendar": bool(int(data.get(b"enable_calendar", b"1"))),
    }


@router.put("/company/flags", response_model=CompanyFlagsResponse)
async def update_flags_endpoint(
    req: CompanyFlagsUpdate, company: str = Depends(get_current_company)
) -> dict[str, bool]:
    """Update feature flags for the current company."""
    return await update_company_flags(company, req)
