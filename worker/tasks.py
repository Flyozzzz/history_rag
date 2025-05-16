import json, asyncio
from redis import asyncio as redis
from tiktoken import get_encoding
from .celery_app import celery
from openai import AsyncOpenAI
enc = get_encoding("cl100k_base")
openai1 = AsyncOpenAI(api_key="sk-pro", base_url="http://178.185.225.236:44048/v1")
def count_tokens(text: str) -> int:
    return len(enc.encode(text))

@celery.task
def summarize_if_needed(uuid: str, threshold: int = 3000):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_summary(uuid, threshold))

async def _async_summary(uuid: str, threshold: int):
    from app.config import get_settings
    settings = get_settings()
    rds = redis.from_url(str(settings.redis_url), decode_responses=False)
    key = f"user:{uuid}:history"
    entries = await rds.xrevrange(key, count=100)
    concatenated = " ".join(
        json.loads(obj[b"data"].decode()).get("content") or "" for _id, obj in entries
    )
    if count_tokens(concatenated) < threshold:
        return
    prompt = (
        "Summarize the following chat history for quick recall by an assistant:\n\n"
        + concatenated
    )

    resp = await openai1.completions.create(model="model", prompt=prompt, max_tokens=5000)
    summary = resp.choices[0].text.strip()
    await rds.hset("summary", uuid, summary)


@celery.task
def update_facts(uuid: str):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_update_facts(uuid))


async def _async_update_facts(uuid: str):
    from app.config import get_settings
    settings = get_settings()
    rds = redis.from_url(str(settings.redis_url), decode_responses=False)
    key = f"user:{uuid}:history"
    entries = await rds.xrange(key)
    facts = []
    for _id, obj in entries:
        msg = json.loads(obj[b"data"].decode())
        content = msg.get("content")
        if msg.get("role") == "user" and content:
            text = content.strip()
            low = text.lower()
            if low.startswith("\u0437\u0430\u043f\u043e\u043c\u043d\u0438") or low.startswith("remember"):
                fact = text.split(":", 1)[1].strip() if ":" in text else text
                facts.append(fact)
    if facts:
        await rds.sadd(f"user:{uuid}:facts", *facts)
