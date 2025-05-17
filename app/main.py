import json, asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from redis import asyncio as redis
import logging
from typing import List, Dict, Any, Tuple
from tiktoken import get_encoding
import gzip
import base64
from openai import AsyncOpenAI
from app.config import get_settings
from app.models import (
    Message,
    AddRequest,
    HistoryResponse,
    SummaryResponse,
    SearchRequest,
    SearchResponse,
    FilterRequest,
    FilterResponse,
)
from app.storage import upload_file
from app.vector import upsert_embedding
from app.transcriber import transcriber
from app.embeddings import embed
from app.vector import semantic_search
from worker.tasks import summarize_if_needed, update_facts

settings = get_settings()
llm  = AsyncOpenAI(api_key=str(settings.openai_api_key), base_url=str(settings.openai_base_url))

enc = get_encoding("cl100k_base")

app = FastAPI(title="History Microservice")

@app.on_event("startup")
async def startup():
    app.state.redis = redis.from_url(str(settings.redis_url), decode_responses=False)

@app.on_event("shutdown")
async def shutdown():
    await app.state.redis.close()

def stream_key(uuid: str) -> str:
    return f"user:{uuid}:history"


async def _check_and_store_fact(rds, uuid: str, msg: Message) -> None:
    if msg.role != "user" or not msg.content:
        return
    text = msg.content.strip()
    low = text.lower()
    if low.startswith("\u0437\u0430\u043f\u043e\u043c\u043d\u0438") or low.startswith("remember"):
        fact = text.split(":", 1)[1].strip() if ":" in text else text
        await rds.sadd(f"user:{uuid}:facts", fact)


async def _aggregate_facts(rds, uuid: str) -> Message | None:
    facts = await rds.smembers(f"user:{uuid}:facts")
    if not facts:
        return None
    text = "; ".join(sorted(f.decode() if isinstance(f, bytes) else f for f in facts))
    return Message(role="user", content=text)

async def _add_to_stream(rds, uuid: str, msg: Message) -> str:
    data = msg.model_dump_json()
    try:
        mid = await rds.xadd(stream_key(uuid), {"data": data})
        await rds.hincrby(f"user:{uuid}:stats:role", msg.role, 1)
        await rds.hincrby(f"user:{uuid}:stats:type", msg.type, 1)
        return mid
    except Exception as exc:
        logging.exception("Failed to store message for %s", uuid)
        raise HTTPException(status_code=500, detail="storage error") from exc

@app.get("/history", response_model=HistoryResponse)
async def get_history(uuid: str = Query(...), limit: int = Query(20)):
    rds = app.state.redis
    entries = await rds.xrevrange(stream_key(uuid), count=limit)
    messages: List[Message] = []
    for _id, obj in reversed(entries):
        msg = Message.model_validate_json(obj[b"data"].decode())
        if msg.extra and msg.extra.get("compressed") and msg.content:
            comp = base64.b64decode(msg.content)
            msg.content = gzip.decompress(comp).decode()
        messages.append(msg)
    return {"messages": messages}


@app.get("/context", response_model=HistoryResponse)
async def get_context(
    uuid: str = Query(...),
    limit: int = Query(10),
    top_k: int = Query(10),
):
    rds = app.state.redis
    entries = await rds.xrevrange(stream_key(uuid), count=limit)
    messages: List[Message] = []
    for _id, obj in reversed(entries):
        msg = Message.model_validate_json(obj[b"data"].decode())
        if msg.extra and msg.extra.get("compressed") and msg.content:
            comp = base64.b64decode(msg.content)
            msg.content = gzip.decompress(comp).decode()
        messages.append(msg)

    q_text = " ".join(m.content or "" for m in messages if m.type == "text")
    relevant: List[Message] = []
    if q_text:
        q_vec = await asyncio.get_running_loop().run_in_executor(None, lambda: embed(q_text))
        ids = await semantic_search(uuid, q_vec, k=top_k)
        for mid in ids:
            row = await rds.xrange(stream_key(uuid), min=mid, max=mid)
            if row:
                rmsg = Message.model_validate_json(row[0][1][b"data"].decode())
                if rmsg.extra and rmsg.extra.get("compressed") and rmsg.content:
                    comp = base64.b64decode(rmsg.content)
                    rmsg.content = gzip.decompress(comp).decode()
                relevant.append(rmsg)

    facts = await _aggregate_facts(rds, uuid)
    summary = await rds.hget("summary", uuid)
    if isinstance(summary, bytes):
        summary = summary.decode()

    return {"messages": messages, "relevant": relevant, "facts": facts, "summary": summary}

@app.post("/add")
async def add_history(req: AddRequest):
    rds = app.state.redis
    ids = []
    for msg in req.messages:
        if msg.type == "image" and msg.extra and "file" in msg.extra:
            upload: UploadFile = msg.extra["file"]  # type: ignore
            payload = await upload.read()
            url = await upload_file(payload, f"{req.uuid}/{upload.filename}", upload.content_type)
            msg.content = url
        elif msg.type == "audio" and msg.extra and "file" in msg.extra:
            upload: UploadFile = msg.extra["file"]  # type: ignore
            payload = await upload.read()
            audio_b64 = base64.b64encode(payload).decode()
            transcription = ""
            if transcriber:
                try:
                    transcription = await transcriber.transcribe_audio(audio_b64)
                except Exception:
                    logging.exception("Audio transcription failed")
            msg.type = "text"
            msg.content = transcription
            if msg.extra is None:
                msg.extra = {}
            msg.extra["transcribed_from"] = "audio"
        if msg.type == "text" and msg.content and len(msg.content) > 500 and msg.importance < 5:
            comp = gzip.compress(msg.content.encode())
            msg.content = base64.b64encode(comp).decode()
            if msg.extra is None:
                msg.extra = {}
            msg.extra["compressed"] = True
        _id = await _add_to_stream(rds, req.uuid, msg)
        ids.append(_id)
        if msg.type == "text" and msg.content:
            asyncio.create_task(_embed_and_insert(req.uuid, _id, msg.content))
            asyncio.create_task(_check_and_store_fact(rds, req.uuid, msg))

    length = await rds.xlen(stream_key(req.uuid))
    if length % 10 == 0:
        summarize_if_needed.delay(req.uuid, settings.summary_token_threshold)
        update_facts.delay(req.uuid)
    return {"stream_ids": ids}

async def _embed_and_insert(uuid: str, message_id: str, text: str):
    loop = asyncio.get_running_loop()
    emb = await loop.run_in_executor(None, lambda: embed(text))
    await upsert_embedding(uuid, message_id, emb)

@app.post("/summary", response_model=SummaryResponse)
async def summarize(uuid: str = Query(...)):
    rds = app.state.redis
    entries = await rds.xrange(stream_key(uuid))
    full_history = [json.loads(obj[b"data"].decode()) for _id, obj in entries]
    messages: list[Dict[str, Any]] = []
    prompt = (
        "Summarize the following user chat history so that an LLM assistant "
        "can quickly recall the user's background, preferences, and key facts.\n\n"
        + json.dumps(full_history, ensure_ascii=False)
    )

    messages.append({"role": "user", "content": prompt})
    logging.info("Summarizing history for %s", uuid)
    try:
        resp = await llm.chat.completions.create(
            model="model", messages=messages, max_tokens=13000
        )
        summary = resp.choices[0].message.content.strip()
        await rds.hset("summary", uuid, summary)
        return {"uuid": uuid, "summary": summary}
    except Exception as exc:
        logging.exception("summary failed for %s", uuid)
        raise HTTPException(status_code=500, detail="summary error") from exc

@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    q_vec = await asyncio.get_running_loop().run_in_executor(None, lambda: embed(req.query))
    ids = await semantic_search(req.uuid, q_vec, k=req.top_k)
    if not ids:
        return {"uuid": req.uuid, "hits": []}

    rds = app.state.redis
    msgs = []
    for mid in ids:
        data = await rds.xrange(stream_key(req.uuid), min=mid, max=mid)
        if data:
            msg = Message.model_validate_json(data[0][1][b"data"].decode())
            if msg.extra and msg.extra.get("compressed") and msg.content:
                comp = base64.b64decode(msg.content)
                msg.content = gzip.decompress(comp).decode()
            msgs.append(msg)
    return {"uuid": req.uuid, "hits": msgs}


filter_fn = {
    "name": "filter_messages",
    "description": "Отметь релевантные индексы; оцени уверенность.",
    "parameters": {
        "type": "object",
        "properties": {
            "keep": {"type": "array", "items": {"type": "integer"}},
            "drop": {"type": "array", "items": {"type": "integer"}},
            "confidence": {           # новое поле
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0
            }
        },
        "required": ["keep", "drop", "confidence"]
    },
}

@app.post("/filter", response_model=FilterResponse)
async def filter_messages(req: FilterRequest):
    q_vec = await asyncio.get_running_loop().run_in_executor(
        None, lambda: embed(req.query)
    )
    ids = await semantic_search(req.uuid, q_vec, k=req.top_k)
    if not ids:
        return {"uuid": req.uuid, "kept": [], "removed": []}

    rds = app.state.redis
    cand: list[Tuple[str, Message]] = []
    for mid in ids:
        row = await rds.xrange(stream_key(req.uuid), min=mid, max=mid)
        if row:
            cmsg = Message.model_validate_json(row[0][1][b"data"].decode())
            if cmsg.extra and cmsg.extra.get("compressed") and cmsg.content:
                comp = base64.b64decode(cmsg.content)
                cmsg.content = gzip.decompress(comp).decode()
            cand.append((mid, cmsg))

    sys = {
        "role": "system",
        "content": (
            "Ты — фильтр. Верни аргументы функции filter_messages: "
            "keep = индексы релевантных, drop = нерелевантных."
            " • confidence — число 0-1, насколько ты уверен, "
            "что keep действительно охватывает всё важное."
        ),
    }
    usr = {
        "role": "user",
        "content": (
            f"Запрос пользователя: «{req.query}». Сообщения:\n" +
            "\n".join(f"{i}. {m.model_dump_json()}" for i, (_, m) in enumerate(cand))
        ),
    }

    try:
        cmp = await llm.chat.completions.create(
            model="model",
            messages=[sys, usr],
            tools=[{"type": "function", "function": filter_fn}],
            tool_choice={"type": "function", "function": {"name": "filter_messages"}},
            temperature=0.1,
        )
    except Exception as exc:
        logging.exception("filter failed for %s", req.uuid)
        raise HTTPException(status_code=500, detail="filter error") from exc

    args = json.loads(
        cmp.choices[0].message.tool_calls[0].function.arguments
    )
    conf = float(args.get("confidence", 0.0))

    keep_idx = set(args["keep"])
    kept, removed = [], []

    for i, (mid, msg) in enumerate(cand):
        if i in keep_idx:
            kept.append(msg)
        else:
            removed.append(mid)
            if req.delete_irrelevant:
                await rds.xdel(stream_key(req.uuid), mid)

    return {"uuid": req.uuid, "kept": kept, "removed": removed, "confidence": conf}