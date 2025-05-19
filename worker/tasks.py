import asyncio
import json
import logging

from openai import AsyncOpenAI
from redis import asyncio as redis

from app.config import get_settings
from app.logging_config import setup_logging

from .celery_app import celery

try:
    from tiktoken import get_encoding

    enc = get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(enc.encode(text))

except Exception:  # pragma: no cover - optional dependency
    enc = None
    logging.getLogger(__name__).warning(
        "tiktoken unavailable, using fallback token counter"
    )

    def count_tokens(text: str) -> int:
        return len(text.split())


setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
openai1 = AsyncOpenAI(
    api_key=settings.openai_api_key, base_url=settings.openai_base_url
)
redis_pool = redis.ConnectionPool.from_url(
    str(settings.redis_url), decode_responses=False
)


@celery.task
def summarize_if_needed(uuid: str, threshold: int = 3000):
    logger.info("Checking if summary needed for %s", uuid)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_summary(uuid, threshold))


async def _async_summary(uuid: str, threshold: int):
    rds = redis.Redis(connection_pool=redis_pool)
    key = f"user:{uuid}:history"
    entries = await rds.xrevrange(key, count=100)
    if not entries:
        return

    last = await rds.get(f"summary:last:{uuid}")
    if isinstance(last, bytes):
        last = last.decode()

    latest_id = entries[0][0]
    if isinstance(latest_id, bytes):
        latest_id = latest_id.decode()

    if last == latest_id:
        return

    concatenated = " ".join(
        json.loads(obj[b"data"].decode()).get("content") or "" for _id, obj in entries
    )
    if count_tokens(concatenated) < threshold:
        return
    prompt = (
        "Summarize the following chat history for quick recall by an assistant:\n\n"
        + concatenated
    )

    resp = await openai1.completions.create(
        model=settings.openai_chat_model, prompt=prompt, max_tokens=5000
    )
    summary = resp.choices[0].text.strip()
    await rds.hset("summary", uuid, summary)
    await rds.set(f"summary:last:{uuid}", latest_id)


@celery.task
def update_facts(uuid: str):
    logger.info("Updating facts for %s", uuid)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_update_facts(uuid))


async def _async_update_facts(uuid: str):
    rds = redis.Redis(connection_pool=redis_pool)
    key = f"user:{uuid}:history"
    last = await rds.get(f"facts:last:{uuid}")
    if isinstance(last, bytes):
        last = last.decode()
    entries = await rds.xrange(key, min=f"({last}" if last else "-", max="+")
    facts = []
    for _id, obj in entries:
        msg = json.loads(obj[b"data"].decode())
        content = msg.get("content")
        if msg.get("role") == "user" and content:
            text = content.strip()
            low = text.lower()
            if low.startswith(
                "\u0437\u0430\u043f\u043e\u043c\u043d\u0438"
            ) or low.startswith("remember"):
                fact = text.split(":", 1)[1].strip() if ":" in text else text
                facts.append(fact)
    if facts:
        logger.debug("Storing %d facts for %s", len(facts), uuid)
        await rds.sadd(f"user:{uuid}:facts", *facts)
    if entries:
        await rds.set(f"facts:last:{uuid}", entries[-1][0])


@celery.task
def generate_tags(uuid: str, limit: int = 20):
    logger.info("Generating tags for %s", uuid)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_generate_tags(uuid, limit))


async def _async_generate_tags(uuid: str, limit: int = 20) -> None:
    from app.embeddings import embed
    from app.encryption import decrypt_text
    from app.history_utils import stream_key
    from app.models import Message
    from app.vector import upsert_embedding

    rds = redis.Redis(connection_pool=redis_pool)
    entries = await rds.xrevrange(stream_key(uuid), count=limit)
    for mid, obj in entries:
        mid_str = mid.decode() if isinstance(mid, bytes) else mid
        if await rds.hget(f"user:{uuid}:msg_tags", mid_str):
            continue
        msg = Message.model_validate_json(decrypt_text(obj[b"data"].decode()))
        if msg.type != "text" or not msg.content:
            continue
        try:
            resp = await openai1.chat.completions.create(
                model=settings.openai_chat_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Generate up to 5 short topic tags. Return comma-separated tags only.",
                    },
                    {"role": "user", "content": msg.content},
                ],
                max_tokens=30,
                temperature=0.2,
            )
            tag_line = resp.choices[0].message.content or ""
            tags = [
                t.strip().lower().replace(" ", "_")
                for t in tag_line.split(",")
                if t.strip()
            ]
        except Exception:
            logger.exception("tag generation failed for %s", uuid)
            continue
        if not tags:
            continue
        await rds.hset(f"user:{uuid}:msg_tags", mid_str, json.dumps(tags))
        for t in tags:
            await rds.sadd(f"user:{uuid}:tags:{t}", mid_str)
        emb = await asyncio.get_running_loop().run_in_executor(
            None, lambda: embed(msg.content)
        )
        await upsert_embedding(uuid, mid_str, emb, tags=tags)


@celery.task
def send_notification(uuid: str, text: str):
    logger.info("Reminder for %s: %s", uuid, text)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_send_notification(uuid, text))


async def _async_send_notification(uuid: str, text: str) -> None:
    from app.config import get_settings
    from app.notify import get_notifier

    settings = get_settings()
    notifier = get_notifier(settings.notification_service)
    try:
        await notifier.send(uuid, text)
    except Exception:
        logger.exception("notification failed")


@celery.task
def check_calendar():
    logger.info("Checking calendar")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_check_calendar())


async def _async_check_calendar():
    from app.config import get_settings
    from app.encryption import decrypt_text
    from app.models import Message
    from app.services.calendar import _batch_check_calendar_events

    settings = get_settings()
    rds = redis.Redis(connection_pool=redis_pool)
    streams = await rds.smembers("calendar:streams")
    for skey_b in streams:
        skey = skey_b.decode() if isinstance(skey_b, bytes) else skey_b
        if not skey.startswith("user:"):
            continue
        uuid = skey.split(":")[1]
        logger.debug("Processing calendar stream %s", uuid)
        last = await rds.get(f"calendar:last:{skey}")
        if isinstance(last, bytes):
            last = last.decode()
        rng = await rds.xrange(skey, min=f"({last}" if last else "-", max="+")
        if not rng:
            continue
        msgs = []
        for mid, obj in rng:
            msg = Message.model_validate_json(decrypt_text(obj[b"data"].decode()))
            msgs.append(msg)
            last = mid
        await _batch_check_calendar_events(rds, uuid, msgs)
        await rds.set(f"calendar:last:{skey}", last)


@celery.task
def process_idle_users():
    logger.info("Processing idle users")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_process_idle_users())


async def _async_process_idle_users():
    from datetime import datetime

    from app.encryption import decrypt_text
    from app.history_utils import stream_key
    from app.models import Message
    from app.services.calendar import _check_and_store_calendar_event

    rds = redis.Redis(connection_pool=redis_pool)
    now = int(datetime.utcnow().timestamp())
    keys = await rds.keys("user:*:data")
    for key_b in keys:
        key = key_b.decode() if isinstance(key_b, bytes) else key_b
        uuid = key.split(":")[1]
        company_id = await rds.hget(key, "company_id")
        if not company_id:
            continue
        company = company_id.decode() if isinstance(company_id, bytes) else company_id
        idle = await rds.hget(f"company:{company}:data", "idle_timeout")
        if not idle:
            continue
        try:
            idle = int(idle)
        except Exception:
            continue
        if idle <= 0:
            continue
        last_seen = await rds.get(f"user:{uuid}:last_seen")
        if not last_seen:
            continue
        last_seen_int = int(
            last_seen.decode() if isinstance(last_seen, bytes) else last_seen
        )
        if now - last_seen_int < idle:
            continue
        summarize_if_needed.delay(uuid, settings.summary_token_threshold)
        update_facts.delay(uuid)
        entry = await rds.xrevrange(stream_key(uuid), count=1)
        if entry:
            msg = Message.model_validate_json(
                decrypt_text(entry[0][1][b"data"].decode())
            )
            await _check_and_store_calendar_event(rds, uuid, msg)
