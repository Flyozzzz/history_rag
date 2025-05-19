import asyncio
import json
import logging
from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.embeddings import embed
from app.encryption import decrypt_text
from app.history_utils import _count_tokens, _decompress_text, _get_tags, stream_key
from app.main import app, settings
from app.models import FilterRequest, FilterResponse, Message
from app.services.company import _ensure_company
from app.services.llm import llm
from app.usage import increment_messages, increment_tokens
from app.vector import semantic_search

router = APIRouter()
logger = logging.getLogger(__name__)


filter_fn = {
    "name": "filter_messages",
    "description": "Отметь релевантные индексы; оцени уверенность.",
    "parameters": {
        "type": "object",
        "properties": {
            "keep": {"type": "array", "items": {"type": "integer"}},
            "drop": {"type": "array", "items": {"type": "integer"}},
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["keep", "drop", "confidence"],
    },
}


@router.post("/filter", response_model=FilterResponse)
async def filter_messages(
    req: FilterRequest, user: tuple[str, str] = Depends(get_current_user)
):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    q_vec = await asyncio.get_running_loop().run_in_executor(
        None, lambda: embed(req.query)
    )
    ids = await semantic_search(req.uuid, q_vec, k=req.top_k)
    if not ids:
        return {"uuid": req.uuid, "kept": [], "removed": []}

    rds = app.state.redis
    cand: List[Tuple[str, Message]] = []
    for mid in ids:
        row = await rds.xrange(stream_key(req.uuid, req.chat_id), min=mid, max=mid)
        if row:
            cmsg = Message.model_validate_json(
                decrypt_text(row[0][1][b"data"].decode())
            )
            if cmsg.extra and cmsg.extra.get("compressed") and cmsg.content:
                cmsg.content = _decompress_text(
                    cmsg.content, cmsg.extra.get("compress_algo")
                )
            mid_str = mid.decode() if isinstance(mid, bytes) else mid
            cmsg.tags = await _get_tags(rds, req.uuid, mid_str)
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
            f"Запрос пользователя: «{req.query}». Сообщения:\n"
            + "\n".join(f"{i}. {m.model_dump_json()}" for i, (_, m) in enumerate(cand))
        ),
    }

    try:
        cmp = await llm.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[sys, usr],
            tools=[{"type": "function", "function": filter_fn}],
            tool_choice={"type": "function", "function": {"name": "filter_messages"}},
            temperature=0.1,
        )
    except Exception as exc:
        logger.exception("filter failed for %s", req.uuid)
        raise HTTPException(status_code=500, detail="filter error") from exc

    args = json.loads(cmp.choices[0].message.tool_calls[0].function.arguments)
    conf = float(args.get("confidence", 0.0))

    keep_idx = set(args["keep"])
    kept, removed = [], []

    for i, (mid, msg) in enumerate(cand):
        if i in keep_idx:
            kept.append(msg)
        else:
            removed.append(mid)
            if req.delete_irrelevant:
                await rds.xdel(stream_key(req.uuid, req.chat_id), mid)
    await increment_messages(rds, company, user_id=uid)
    await increment_tokens(rds, company, _count_tokens(req.query), uid)

    return {"uuid": req.uuid, "kept": kept, "removed": removed, "confidence": conf}
