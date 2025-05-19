import json
import logging
import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis import asyncio as redis

from app.company_auth import router as company_auth_router
from app.config import get_settings
from app.history_utils import _add_to_stream, stream_key
from app.models import Message
from app.services.llm import llm

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="History Microservice")
BASE_DIR = os.path.dirname(__file__)
try:
    templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(BASE_DIR, "static")),
        name="static",
    )
except Exception:
    templates = None


@app.on_event("startup")
async def startup():
    logger.info("Starting up application")
    app.state.redis = redis.from_url(str(settings.redis_url), decode_responses=False)


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down application")
    await app.state.redis.close()


from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.calendar import router as calendar_router
from app.routes.facts import router as facts_router
from app.routes.filtering import router as filtering_router
from app.routes.history import router as history_router
from app.routes.messages import router as messages_router

app.include_router(company_auth_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(history_router)
app.include_router(messages_router)
app.include_router(calendar_router)
app.include_router(facts_router)
app.include_router(filtering_router)
