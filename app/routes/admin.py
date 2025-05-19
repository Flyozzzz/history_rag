from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import get_current_user
from app.company_auth import get_current_company

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/company/login_page", response_class=HTMLResponse)
async def company_login_page(request: Request):
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    return templates.TemplateResponse(
        "company_login.html", {"request": request, "title": "Company Login"}
    )


@router.post("/company/login_page", response_class=HTMLResponse)
async def company_login_post(
    request: Request, name: str = Form(...), password: str = Form(...)
):
    from app.company_auth import login_company
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    try:
        token = await login_company(name, password)
    except HTTPException:
        token = None
    if token:
        response = RedirectResponse("/company/dashboard", status_code=302)
        response.set_cookie("company_token", token, httponly=True)
        return response
    return templates.TemplateResponse(
        "company_login.html",
        {"request": request, "title": "Company Login", "token": token, "name": name},
    )


@router.get("/company/register_page", response_class=HTMLResponse)
async def company_register_page(request: Request):
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    return templates.TemplateResponse(
        "company_register.html",
        {
            "request": request,
            "title": "Register Company",
            "enable_summary": True,
            "enable_facts": True,
            "enable_calendar": True,
        },
    )


@router.post("/company/register_page", response_class=HTMLResponse)
async def company_register_post(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    enable_summary: bool = Form(False),
    enable_facts: bool = Form(False),
    enable_calendar: bool = Form(False),
):
    from app.company_auth import register_company
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    try:
        token = await register_company(
            name,
            password,
            enable_summary=enable_summary,
            enable_facts=enable_facts,
            enable_calendar=enable_calendar,
        )
    except HTTPException:
        token = None
    return templates.TemplateResponse(
        "company_register.html",
        {
            "request": request,
            "title": "Register Company",
            "token": token,
            "name": name,
            "enable_summary": enable_summary,
            "enable_facts": enable_facts,
            "enable_calendar": enable_calendar,
        },
    )


@router.get("/user/login_page", response_class=HTMLResponse)
async def user_login_page(request: Request):
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    return templates.TemplateResponse(
        "user_login.html", {"request": request, "title": "User Login"}
    )


@router.post("/user/login_page", response_class=HTMLResponse)
async def user_login_post(
    request: Request, uuid: str = Form(...), password: str = Form(...)
):
    from app.auth import login_user
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    try:
        token = await login_user(uuid, password)
    except HTTPException:
        token = None
    return templates.TemplateResponse(
        "user_login.html",
        {"request": request, "title": "User Login", "token": token, "uuid": uuid},
    )


@router.get("/user/register_page", response_class=HTMLResponse)
async def user_register_page(request: Request):
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    return templates.TemplateResponse(
        "user_register.html", {"request": request, "title": "Register User"}
    )


@router.post("/user/register_page", response_class=HTMLResponse)
async def user_register_post(
    request: Request,
    uuid: str = Form(...),
    password: str = Form(...),
    company_id: str = Form(...),
):
    from app.auth import register_user
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    try:
        token = await register_user(uuid, password, company_id)
    except HTTPException:
        token = None
    return templates.TemplateResponse(
        "user_register.html",
        {
            "request": request,
            "title": "Register User",
            "token": token,
            "uuid": uuid,
            "company_id": company_id,
        },
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request):
    from app.main import templates

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    return templates.TemplateResponse(
        "index.html", {"request": request, "title": "Admin"}
    )


@router.get("/admin/history", response_class=HTMLResponse)
async def admin_history(
    request: Request, uuid: str, token: str, limit: int = 20, chat_id: str | None = None
):
    from app.main import templates
    from app.routes.history import get_history
    from app.services.company import _ensure_company

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    user, company = await get_current_user(authorization=f"Bearer {token}")
    if user != uuid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(user, company)
    resp = await get_history(
        uuid=uuid, limit=limit, chat_id=chat_id, user=(user, company)
    )
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "messages": resp["messages"],
            "uuid": uuid,
            "title": "History",
        },
    )


@router.get("/admin/calendar", response_class=HTMLResponse)
async def admin_calendar(request: Request, uuid: str, token: str):
    from app.main import templates
    from app.routes.calendar import get_calendar
    from app.services.company import _ensure_company

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    user, company = await get_current_user(authorization=f"Bearer {token}")
    if user != uuid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(user, company)
    resp = await get_calendar(uuid=uuid, user=(user, company))
    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "events": resp["events"],
            "uuid": uuid,
            "title": "Calendar",
        },
    )


@router.get("/company/dashboard", response_class=HTMLResponse)
async def company_dashboard(
    request: Request, company: str = Depends(get_current_company)
):
    from app.main import app, settings, templates
    from app.usage import calculate_cost, calculate_user_cost, get_usage, get_user_usage

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    rds = app.state.redis
    users_raw = await rds.smembers(f"company:{company}:users")
    users = sorted(u.decode() if isinstance(u, bytes) else u for u in users_raw)
    usage = await get_usage(rds, company)
    cost = await calculate_cost(rds, company, settings)
    user_usage: dict[str, dict[str, Any]] = {}
    labels: list[str] = []
    messages_data: list[int] = []
    tokens_data: list[int] = []
    cost_data: list[float] = []
    for u in users:
        u_usage = await get_user_usage(rds, company, u)
        u_cost = await calculate_user_cost(rds, company, u, settings)
        user_usage[u] = {
            "messages": u_usage["messages"],
            "tokens": u_usage["tokens"],
            "cost": f"{u_cost:.2f}",
        }
        labels.append(u)
        messages_data.append(u_usage["messages"])
        tokens_data.append(u_usage["tokens"])
        cost_data.append(round(u_cost, 2))
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "company": company,
            "users": users,
            "usage": usage,
            "user_usage": user_usage,
            "cost": f"{cost:.2f}",
            "labels": labels,
            "messages_data": messages_data,
            "tokens_data": tokens_data,
            "cost_data": cost_data,
            "title": "Dashboard",
        },
    )


@router.get("/company/history", response_class=HTMLResponse)
async def company_history(
    request: Request,
    uuid: str,
    limit: int = 20,
    chat_id: str | None = None,
    company: str = Depends(get_current_company),
):
    from app.main import templates
    from app.routes.history import get_history
    from app.services.company import _ensure_company

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    await _ensure_company(uuid, company)
    resp = await get_history(
        uuid=uuid, limit=limit, chat_id=chat_id, user=(uuid, company)
    )
    return templates.TemplateResponse(
        "user_history.html",
        {
            "request": request,
            "messages": resp["messages"],
            "uuid": uuid,
            "title": "History",
        },
    )


@router.get("/company/facts", response_class=HTMLResponse)
async def company_facts(
    request: Request,
    uuid: str,
    company: str = Depends(get_current_company),
):
    from app.main import templates
    from app.routes.facts import list_facts
    from app.services.company import _ensure_company

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    await _ensure_company(uuid, company)
    resp = await list_facts(uuid=uuid, user=(uuid, company))
    return templates.TemplateResponse(
        "user_facts.html",
        {"request": request, "facts": resp["facts"], "uuid": uuid, "title": "Facts"},
    )


@router.get("/company/summary", response_class=HTMLResponse)
async def company_summary(
    request: Request,
    uuid: str,
    chat_id: str | None = None,
    company: str = Depends(get_current_company),
):
    from app.main import templates
    from app.routes.messages import summarize
    from app.services.company import _ensure_company

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    await _ensure_company(uuid, company)
    resp = await summarize(uuid=uuid, chat_id=chat_id, user=(uuid, company))
    return templates.TemplateResponse(
        "user_summary.html",
        {
            "request": request,
            "summary": resp["summary"],
            "uuid": uuid,
            "title": "Summary",
        },
    )


@router.get("/company/calendar", response_class=HTMLResponse)
async def company_calendar(
    request: Request,
    uuid: str,
    company: str = Depends(get_current_company),
):
    from app.main import templates
    from app.routes.calendar import get_calendar
    from app.services.company import _ensure_company

    if not templates:
        raise HTTPException(status_code=500, detail="templates not available")
    await _ensure_company(uuid, company)
    resp = await get_calendar(uuid=uuid, user=(uuid, company))
    return templates.TemplateResponse(
        "user_calendar.html",
        {
            "request": request,
            "events": resp["events"],
            "uuid": uuid,
            "title": "Calendar",
        },
    )
