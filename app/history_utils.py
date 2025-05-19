import base64
import gzip
import json
import logging
import re

from fastapi import HTTPException

from app.config import get_settings
from app.encryption import encrypt_text
from app.models import Message

logger = logging.getLogger(__name__)
settings = get_settings()


async def _get_tags(rds, uuid: str, mid: str) -> list[str] | None:
    raw = await rds.hget(f"user:{uuid}:msg_tags", mid)
    if raw:
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            return json.loads(raw)
        except Exception:
            return []
    return None


def _compress_text(text: str) -> str:
    data = text.encode()
    if settings.compression_algorithm == "gzip":
        data = gzip.compress(data)
    return base64.b64encode(data).decode()


def _decompress_text(data_b64: str, algo: str | None = None) -> str:
    raw = base64.b64decode(data_b64)
    algorithm = algo or settings.compression_algorithm
    if algorithm == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode()


def _count_tokens(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())


def stream_key(uuid: str, chat_id: str | None = None) -> str:
    """Return the Redis stream key for a user's history.

    If ``chat_id`` is provided a chat-specific key is returned, otherwise the
    per-user history key is used. All unsafe characters are replaced with an
    underscore to keep Redis keys valid.
    """

    safe_uuid = re.sub(r"[^\w-]", "_", uuid)
    if chat_id:
        safe_chat = re.sub(r"[^\w-]", "_", chat_id)
        return f"chat:{safe_chat}:history"
    return f"user:{safe_uuid}:history"


async def _add_to_stream(
    rds, uuid: str, msg: Message, chat_id: str | None = None
) -> str:
    """Encrypt ``msg`` and append it to the appropriate Redis stream.

    The function also updates per-user statistics about message roles and
    types. On failure a HTTP 500 error is raised.
    """

    data = encrypt_text(msg.model_dump_json())
    try:
        skey = stream_key(uuid, chat_id)
        mid = await rds.xadd(skey, {"data": data})
        await rds.sadd("calendar:streams", skey)
        await rds.hincrby(f"user:{uuid}:stats:role", msg.role, 1)
        await rds.hincrby(f"user:{uuid}:stats:type", msg.type, 1)
        return mid
    except Exception as exc:
        logger.exception("Failed to store message for %s", uuid)
        raise HTTPException(status_code=500, detail="storage error") from exc
