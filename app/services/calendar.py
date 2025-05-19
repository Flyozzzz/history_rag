import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import Message
from worker.tasks import send_notification

logger = logging.getLogger(__name__)


def _to_utc(dt: datetime, tz: str) -> datetime:
    """Convert naive or tz-aware datetime from tz to UTC."""
    try:
        tzinfo = ZoneInfo(tz)
    except Exception:
        tzinfo = ZoneInfo("UTC")
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=tzinfo)
    else:
        local = dt.astimezone(tzinfo)
    return local.astimezone(ZoneInfo("UTC"))


async def _list_events(rds, uuid: str):
    rows = await rds.zrange(f"user:{uuid}:calendar", 0, -1, withscores=True)
    events = []
    for i, (raw, ts) in enumerate(rows):
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        events.append(
            {
                "index": i,
                "when": datetime.fromtimestamp(ts, tz=ZoneInfo("UTC")).isoformat(),
                "text": data.get("text"),
                "tz": data.get("tz", "UTC"),
            }
        )
    return events


async def _add_event(rds, uuid: str, when: str, text: str, tz: str = "UTC"):
    dt = datetime.fromisoformat(when)
    when_utc = _to_utc(dt, tz)
    await rds.zadd(
        f"user:{uuid}:calendar",
        {json.dumps({"text": text, "tz": tz}): int(when_utc.timestamp())},
    )
    send_notification.apply_async(args=[uuid, text], eta=when_utc)
    return {"status": "added"}


async def _update_event(
    rds,
    uuid: str,
    index: int,
    when: str | None = None,
    text: str | None = None,
    tz: str | None = None,
):
    rows = await rds.zrange(f"user:{uuid}:calendar", index, index, withscores=True)
    if not rows:
        return {"status": "not_found"}
    raw, score = rows[0]
    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    if text is not None:
        data["text"] = text
    if tz is not None:
        data["tz"] = tz
    ts = int(score)
    if when:
        ts = int(
            _to_utc(
                datetime.fromisoformat(when), data.get("tz", tz or "UTC")
            ).timestamp()
        )
    await rds.zremrangebyrank(f"user:{uuid}:calendar", index, index)
    await rds.zadd(f"user:{uuid}:calendar", {json.dumps(data): ts})
    return {"status": "updated"}


async def _delete_event(rds, uuid: str, index: int):
    await rds.zremrangebyrank(f"user:{uuid}:calendar", index, index)
    return {"status": "deleted"}


async def _check_and_store_calendar_event(
    rds, uuid: str, msg: Message, tz: str = "UTC"
) -> None:
    """Analyze a user message and manage calendar events."""
    from app.main import settings
    from app.services.llm import llm

    if msg.role != "user" or not msg.content:
        return

    text = msg.content.strip()
    low = text.lower()

    if not any(
        k in low
        for k in [
            "\u043d\u0430\u043f\u043e\u043c",
            "remind",
            "\u043a\u0430\u043b\u0435\u043d\u0434\u0430\u0440",
            "\u0432\u0441\u0442\u0440\u0435\u0447",
            "\u0443\u0434\u0430\u043b",
            "\u0438\u0437\u043c\u0435\u043d",
            "\u043f\u043e\u043a\u0430\u0436",
        ]
    ):
        return

    when: datetime | None = None
    if "\u043d\u0430\u043f\u043e\u043c\u043d\u0438" in low or "remind" in low:
        import re
        from datetime import time, timedelta

        m = re.search(
            r"(\u0437\u0430\u0432\u0442\u0440\u0430|\u0441\u0435\u0433\u043e\u0434\u043d\u044f).*?(\d{1,2})[:.](\d{2})",
            low,
        )
        if m:
            hour = int(m.group(2))
            minute = int(m.group(3))
            base_day = datetime.utcnow().date()
            if m.group(1) == "\u0437\u0430\u0432\u0442\u0440\u0430":
                base_day += timedelta(days=1)
            when = datetime.combine(base_day, time(hour=hour, minute=minute))

    if when:
        when_utc = _to_utc(when, tz)
        await rds.zadd(
            f"user:{uuid}:calendar",
            {json.dumps({"text": text, "tz": tz}): int(when_utc.timestamp())},
        )
        send_notification.apply_async(args=[uuid, text], eta=when_utc)
        return

    try:
        now = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
        msg_ts = msg.ts
        if msg_ts.tzinfo is None:
            msg_ts = msg_ts.replace(tzinfo=ZoneInfo("UTC"))
        sys_msg = {
            "role": "system",
            "content": (
                f"Current time is {now.isoformat()} ({now.strftime('%A')}). "
                f"Message time is {msg_ts.isoformat()} ({msg_ts.strftime('%A')}). "
                "Extract calendar command. Use add_event, update_event, delete_event or list_events if appropriate. If nothing matches, do nothing."
            ),
        }
        usr_msg = {"role": "user", "content": text}
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_events",
                    "description": "List calendar events",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_event",
                    "description": "Add event to calendar",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "when": {
                                "type": "string",
                                "description": "ISO8601 datetime",
                            },
                            "text": {"type": "string"},
                            "tz": {"type": "string", "default": tz},
                        },
                        "required": ["when", "text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_event",
                    "description": "Update event by index",
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
                    "description": "Delete event by index",
                    "parameters": {
                        "type": "object",
                        "properties": {"index": {"type": "integer"}},
                        "required": ["index"],
                    },
                },
            },
        ]
        messages = [sys_msg, usr_msg]
        while True:
            cmp = await llm.chat.completions.create(
                model=settings.openai_chat_model, messages=messages, tools=tools
            )
            call_msg = cmp.choices[0].message
            if not call_msg.tool_calls:
                break
            messages.append({"role": "assistant", "tool_calls": call_msg.tool_calls})
            for call in call_msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "add_event" and args.get("when"):
                    when = datetime.fromisoformat(args["when"])
                    text = args.get("text", text)
                    tz = args.get("tz", tz)
                    when_utc = _to_utc(when, tz)
                    await rds.zadd(
                        f"user:{uuid}:calendar",
                        {
                            json.dumps({"text": text, "tz": tz}): int(
                                when_utc.timestamp()
                            )
                        },
                    )
                    send_notification.apply_async(args=[uuid, text], eta=when_utc)
                    result = {"status": "added"}
                elif call.function.name == "update_event":
                    result = await _update_event(
                        rds,
                        uuid,
                        args.get("index"),
                        args.get("when"),
                        args.get("text"),
                        args.get("tz"),
                    )
                elif call.function.name == "delete_event":
                    result = await _delete_event(rds, uuid, args.get("index"))
                elif call.function.name == "list_events":
                    result = await _list_events(rds, uuid)
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
    except Exception:
        logger.exception("calendar extraction failed")


async def _batch_check_calendar_events(
    rds, uuid: str, messages: list[Message], tz: str = "UTC"
) -> None:
    """Process multiple messages for calendar commands."""

    if not messages:
        return
    for m in messages:
        await _check_and_store_calendar_event(rds, uuid, m, tz=tz)

    combined = " ".join(
        m.content.strip() for m in messages if m.role == "user" and m.content
    )
    if combined:
        combo_msg = Message(role="user", content=combined, ts=messages[-1].ts)
        await _check_and_store_calendar_event(rds, uuid, combo_msg, tz=tz)
