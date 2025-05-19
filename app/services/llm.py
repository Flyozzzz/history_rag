import logging

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

llm = AsyncOpenAI(
    api_key=str(settings.openai_api_key),
    base_url=str(settings.openai_base_url),
)

__all__ = ["llm"]
