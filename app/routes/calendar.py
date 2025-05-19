import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.main import app, settings
from app.models import (
    CalendarChatRequest,
    CalendarDeleteRequest,
    CalendarEvent,
    CalendarResponse,
    CalendarUpdateRequest,
    Message,
)
from app.services.calendar import (
    _add_event,
    _delete_event,
    _list_events,
    _to_utc,
    _update_event,
)
from app.services.company import _ensure_company
from app.services.llm import llm
from worker.tasks import send_notification

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/calendar", response_model=CalendarResponse)
async def get_calendar(
    uuid: str = Query(...),
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    rows = await rds.zrange(f"user:{uuid}:calendar", 0, -1, withscores=True)
    events = []
    for raw, ts in rows:
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        tz = data.get("tz", "UTC")
        when = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC")).astimezone(ZoneInfo(tz))
        events.append(
            CalendarEvent(
                when=when, text=data["text"], chat_id=data.get("chat_id"), tz=tz
            )
        )
    return {"uuid": uuid, "events": events}


@router.post("/reminder")
async def set_reminder(
    uuid: str = Query(...),
    when: datetime = Query(...),
    text: str = Query(...),
    tz: str = Query("UTC"),
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    when_utc = _to_utc(when, tz)
    await rds.zadd(
        f"user:{uuid}:calendar",
        {json.dumps({"text": text, "tz": tz}): int(when_utc.timestamp())},
    )
    send_notification.apply_async(args=[uuid, text], eta=when_utc)
    return {"status": "scheduled"}


@router.put("/calendar/{index}")
async def update_calendar(
    index: int,
    req: CalendarUpdateRequest,
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    rows = await rds.zrange(f"user:{req.uuid}:calendar", index, index, withscores=True)
    if not rows:
        raise HTTPException(status_code=404, detail="not found")
    raw, score = rows[0]
    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    if req.text is not None:
        data["text"] = req.text
    ts = int(req.when.timestamp()) if req.when else int(score)
    await rds.zremrangebyrank(f"user:{req.uuid}:calendar", index, index)
    await rds.zadd(f"user:{req.uuid}:calendar", {json.dumps(data): ts})
    return {"status": "updated"}


@router.delete("/calendar/{index}")
async def delete_calendar(
    index: int,
    req: CalendarDeleteRequest,
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    await rds.zremrangebyrank(f"user:{req.uuid}:calendar", index, index)
    return {"status": "deleted"}


@router.post("/calendar/assistant", response_model=Message)
async def calendar_assistant(
    req: CalendarChatRequest, user: tuple[str, str] = Depends(get_current_user)
):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    sys = {
        "role": "system",
        "content": (
            "Ты помощник по календарю. Используй функции чтобы управлять событиями пользователя. "
            "не забудь сначала проверить список календаря"
        ),
    }
    usr = {"role": "user", "content": req.query}

    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_events",
                "description": "Получить все события календаря пользователя",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_event",
                "description": "Добавить событие в календарь",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "when": {"type": "string", "description": "ISO8601 datetime"},
                        "text": {"type": "string"},
                        "tz": {"type": "string", "default": "UTC"},
                    },
                    "required": ["when", "text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_event",
                "description": "Изменить событие по индексу",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "when": {"type": "string"},
                        "text": {"type": "string"},
                        "tz": {"type": "string"},
                    },
                    "required": ["index"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_event",
                "description": "Удалить событие по индексу",
                "parameters": {
                    "type": "object",
                    "properties": {"index": {"type": "integer"}},
                    "required": ["index"],
                },
            },
        },
    ]

    messages = [sys, usr]

    while True:
        cmp = await llm.chat.completions.create(
            model=settings.openai_chat_model, messages=messages, tools=tools
        )
        msg = cmp.choices[0].message
        if msg.tool_calls:
            messages.append({"role": "assistant", "tool_calls": msg.tool_calls})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "list_events":
                    result = await _list_events(rds, req.uuid)
                elif call.function.name == "add_event":
                    result = await _add_event(
                        rds,
                        req.uuid,
                        args.get("when"),
                        args.get("text"),
                        args.get("tz", req.tz),
                    )
                elif call.function.name == "update_event":
                    result = await _update_event(
                        rds,
                        req.uuid,
                        args.get("index"),
                        args.get("when"),
                        args.get("text"),
                        args.get("tz"),
                    )
                elif call.function.name == "delete_event":
                    result = await _delete_event(rds, req.uuid, args.get("index"))
                else:
                    result = {"status": "unknown"}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            continue
        return Message(role="assistant", content=msg.content)
