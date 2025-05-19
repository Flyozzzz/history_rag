import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.embeddings import embed
from app.encryption import decrypt_text
from app.history_utils import _decompress_text, _get_tags, stream_key
from app.main import app
from app.models import HistoryResponse, Message
from app.services.company import _company_feature_enabled, _ensure_company
from app.services.facts import _aggregate_facts
from app.vector import semantic_search

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    uuid: str = Query(...),
    limit: int = Query(20),
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
    entries = await rds.xrevrange(stream_key(uuid, chat_id), count=limit)
    messages: List[Message] = []
    for _id, obj in reversed(entries):
        msg = Message.model_validate_json(decrypt_text(obj[b"data"].decode()))
        if msg.extra and msg.extra.get("compressed") and msg.content:
            msg.content = _decompress_text(msg.content, msg.extra.get("compress_algo"))
        mid = _id.decode() if isinstance(_id, bytes) else _id
        msg.tags = await _get_tags(rds, uuid, mid)
        messages.append(msg)
    return {"messages": messages}


@router.get("/context", response_model=HistoryResponse)
async def get_context(
    uuid: str = Query(...),
    limit: int = Query(10),
    top_k: int = Query(10),
    chat_id: str | None = Query(None),
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    entries = await rds.xrevrange(stream_key(uuid, chat_id), count=limit)
    messages: List[Message] = []
    seen_ids: set[str] = set()
    for _id, obj in reversed(entries):
        sid = _id.decode() if isinstance(_id, bytes) else _id
        seen_ids.add(sid)
        msg = Message.model_validate_json(decrypt_text(obj[b"data"].decode()))
        if msg.extra and msg.extra.get("compressed") and msg.content:
            msg.content = _decompress_text(msg.content, msg.extra.get("compress_algo"))
        msg.tags = await _get_tags(rds, uuid, sid)
        messages.append(msg)

    q_text = " ".join(m.content or "" for m in messages if m.type == "text")
    relevant: List[Message] = []
    if q_text:
        q_vec = await asyncio.get_running_loop().run_in_executor(
            None, lambda: embed(q_text)
        )
        ids = await semantic_search(uuid, q_vec, k=top_k)
        for mid in ids:
            smid = mid.decode() if isinstance(mid, bytes) else mid
            if smid in seen_ids:
                continue
            row = await rds.xrange(stream_key(uuid, chat_id), min=mid, max=mid)
            if row:
                rmsg = Message.model_validate_json(
                    decrypt_text(row[0][1][b"data"].decode())
                )
                if rmsg.extra and rmsg.extra.get("compressed") and rmsg.content:
                    rmsg.content = _decompress_text(
                        rmsg.content, rmsg.extra.get("compress_algo")
                    )
                rmsg.tags = await _get_tags(rds, uuid, smid)
                relevant.append(rmsg)

    facts = await _aggregate_facts(rds, uuid)
    summary = await rds.hget("summary", uuid)
    if isinstance(summary, bytes):
        summary = summary.decode()

    return {
        "messages": messages,
        "relevant": relevant,
        "facts": facts,
        "summary": summary,
    }
