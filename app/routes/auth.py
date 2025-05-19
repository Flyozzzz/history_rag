import logging

from fastapi import APIRouter, Header, HTTPException

from app.auth import login_user, register_user
from app.company_auth import login_company, register_company
from app.config import get_settings
from app.models import (
    AuthResponse,
    CompanyAuthResponse,
    CompanyLoginRequest,
    CompanyRegisterRequest,
    LoginRequest,
    RegisterRequest,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, x_admin_key: str | None = Header(None)):
    logger.info("Register endpoint called for %s", req.username)
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="admin key required")
    token = await register_user(req.username, req.password, req.company_id)
    return {"uuid": req.username, "token": token}


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    logger.info("Login endpoint called for %s", req.username)
    token = await login_user(req.username, req.password)
    return {"uuid": req.username, "token": token}


@router.post("/register_company", response_model=CompanyAuthResponse)
async def register_company_endpoint(
    req: CompanyRegisterRequest, x_admin_key: str | None = Header(None)
):
    logger.info("Register company endpoint called for %s", req.name)
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="admin key required")
    token = await register_company(req.name, req.password, req.idle_timeout)
    return {"name": req.name, "token": token}


@router.post("/login_company", response_model=CompanyAuthResponse)
async def login_company_endpoint(req: CompanyLoginRequest):
    logger.info("Company login endpoint called for %s", req.name)
    token = await login_company(req.name, req.password)
    return {"name": req.name, "token": token}
