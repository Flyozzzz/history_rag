import asyncio
import base64
import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile

from app.auth import get_current_user
from app.embeddings import embed
from app.encryption import decrypt_text
from app.history_utils import (
    _add_to_stream,
    _compress_text,
    _count_tokens,
    _decompress_text,
    _get_tags,
    stream_key,
)
from app.main import app, settings
from app.models import (
    AddRequest,
    Message,
    SearchRequest,
    SearchResponse,
    SummaryResponse,
)
from app.services.calendar import _check_and_store_calendar_event
from app.services.company import _company_feature_enabled, _ensure_company
from app.services.facts import _check_and_store_fact
from app.services.llm import llm
from app.services.messages import _embed_and_insert
from app.storage import upload_file
from app.transcriber import transcriber
from app.usage import increment_messages, increment_tokens
from app.vector import semantic_search
from worker.tasks import generate_tags, summarize_if_needed, update_facts

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/add")
async def add_history(
    req: AddRequest, user: tuple[str, str] = Depends(get_current_user)
):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    summary_enabled = await _company_feature_enabled(company, "enable_summary")
    facts_enabled = await _company_feature_enabled(company, "enable_facts")
    calendar_enabled = await _company_feature_enabled(company, "enable_calendar")
    await rds.set(f"user:{req.uuid}:last_seen", int(datetime.utcnow().timestamp()))
    ids = []
    token_count = 0
    for msg in req.messages:
        if msg.extra and "file" in msg.extra:
            upload: UploadFile = msg.extra.pop("file")
            payload = await upload.read()
            url = await upload_file(
                payload, f"{req.uuid}/{upload.filename}", upload.content_type
            )
            if msg.extra is None:
                msg.extra = {}
            msg.extra.update(
                {
                    "url": url,
                    "size": len(payload),
                    "format": upload.content_type,
                }
            )

            if msg.type == "audio":
                audio_b64 = base64.b64encode(payload).decode()
                transcription = ""
                if transcriber:
                    try:
                        transcription = await transcriber.transcribe_audio(audio_b64)
                    except Exception:
                        logger.exception("Audio transcription failed")
                msg.type = "text"
                msg.content = transcription
                msg.extra["transcribed_from"] = "audio"
            else:
                msg.content = url
        if (
            msg.type == "text"
            and msg.content
            and len(msg.content) > settings.compression_threshold
            and msg.importance < 5
        ):
            msg.content = _compress_text(msg.content)
            if msg.extra is None:
                msg.extra = {}
            msg.extra["compressed"] = True
            msg.extra["compress_algo"] = settings.compression_algorithm
        _id = await _add_to_stream(rds, req.uuid, msg, req.chat_id)
        ids.append(_id)
        if msg.type == "text" and msg.content:
            asyncio.create_task(_embed_and_insert(req.uuid, _id, msg.content))
            if facts_enabled:
                asyncio.create_task(_check_and_store_fact(rds, req.uuid, msg))
            if calendar_enabled:
                asyncio.create_task(_check_and_store_calendar_event(rds, req.uuid, msg))
            token_count += _count_tokens(msg.content)

    await increment_messages(rds, company, len(req.messages), req.uuid)
    if token_count:
        await increment_tokens(rds, company, token_count, req.uuid)

    length = await rds.xlen(stream_key(req.uuid, req.chat_id))
    if length % 10 == 0:
        if summary_enabled:
            summarize_if_needed.delay(req.uuid, settings.summary_token_threshold)
        if facts_enabled:
            update_facts.delay(req.uuid)
        generate_tags.delay(req.uuid)
    return {"stream_ids": ids}


@router.post("/summary", response_model=SummaryResponse)
async def summarize(
    uuid: str = Query(...),
    chat_id: str | None = Query(None),
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    if not await _company_feature_enabled(company, "enable_summary"):
        raise HTTPException(status_code=403, detail="summary disabled")
    rds = app.state.redis
    entries = await rds.xrange(stream_key(uuid, chat_id))
    full_history = [
        json.loads(decrypt_text(obj[b"data"].decode())) for _id, obj in entries
    ]
    token_count = sum(_count_tokens(m.get("content")) for m in full_history)
    messages: list[Dict[str, Any]] = []
    prompt = (
        "Summarize the following user chat history so that an LLM assistant "
        "can quickly recall the user's background, preferences, and key facts.\n\n"
        + json.dumps(full_history, ensure_ascii=False)
    )

    messages.append({"role": "user", "content": prompt})
    logger.info("Summarizing history for %s", uuid)
    try:
        resp = await llm.chat.completions.create(
            model=settings.openai_chat_model, messages=messages, max_tokens=13000
        )
        summary = resp.choices[0].message.content.strip()
        await rds.hset("summary", uuid, summary)
        await increment_messages(rds, company, user_id=uuid)
        if token_count:
            await increment_tokens(rds, company, token_count, uuid)
        return {"uuid": uuid, "summary": summary}
    except Exception as exc:
        logger.exception("summary failed for %s", uuid)
        raise HTTPException(status_code=500, detail="summary error") from exc


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, user: tuple[str, str] = Depends(get_current_user)):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    q_vec = await asyncio.get_running_loop().run_in_executor(
        None, lambda: embed(req.query)
    )
    ids = await semantic_search(req.uuid, q_vec, k=req.top_k, tags=req.tags)
    if not ids:
        await increment_messages(rds, company, user_id=uid)
        await increment_tokens(rds, company, _count_tokens(req.query), uid)
        return {"uuid": req.uuid, "hits": []}

    msgs = []
    for mid in ids:
        data = await rds.xrange(stream_key(req.uuid, req.chat_id), min=mid, max=mid)
        if data:
            msg = Message.model_validate_json(
                decrypt_text(data[0][1][b"data"].decode())
            )
            if msg.extra and msg.extra.get("compressed") and msg.content:
                msg.content = _decompress_text(
                    msg.content, msg.extra.get("compress_algo")
                )
            mid_str = mid.decode() if isinstance(mid, bytes) else mid
            msg.tags = await _get_tags(rds, req.uuid, mid_str)
            msgs.append(msg)
    await increment_messages(rds, company, user_id=uid)
    await increment_tokens(rds, company, _count_tokens(req.query), uid)
    return {"uuid": req.uuid, "hits": msgs}


@router.get("/search_by_tag", response_model=SearchResponse)
async def search_by_tag(
    uuid: str = Query(...),
    tag: str = Query(...),
    limit: int = Query(10),
    chat_id: str | None = Query(None),
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    ids = await rds.smembers(f"user:{uuid}:tags:{tag}")
    if not ids:
        return {"uuid": uuid, "hits": []}
    msgs: list[Message] = []
    for mid_b in list(ids)[:limit]:
        mid = mid_b.decode() if isinstance(mid_b, bytes) else mid_b
        row = await rds.xrange(stream_key(uuid, chat_id), min=mid, max=mid)
        if row:
            msg = Message.model_validate_json(decrypt_text(row[0][1][b"data"].decode()))
            if msg.extra and msg.extra.get("compressed") and msg.content:
                msg.content = _decompress_text(
                    msg.content, msg.extra.get("compress_algo")
                )
            msg.tags = await _get_tags(rds, uuid, mid)
            msgs.append(msg)
    return {"uuid": uuid, "hits": msgs}
