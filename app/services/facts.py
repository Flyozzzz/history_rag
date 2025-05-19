import json
import logging

from app.main import settings
from app.models import Message
from app.services.llm import llm

logger = logging.getLogger(__name__)


async def _check_and_store_fact(rds, uuid: str, msg: Message) -> None:
    """Analyze a user message and store or manage facts."""
    if msg.role != "user" or not msg.content:
        return

    text = msg.content.strip()
    low = text.lower()

    if low.startswith("\u0437\u0430\u043f\u043e\u043c\u043d\u0438") or low.startswith(
        "remember"
    ):
        fact = text.split(":", 1)[1].strip() if ":" in text else text
        await _add_fact(rds, uuid, fact)
        return

    try:
        sys_msg = {
            "role": "system",
            "content": (
                "Extract fact command. Use add_fact, delete_fact or list_facts if appropriate. "
                "If nothing matches, do nothing."
            ),
        }
        usr_msg = {"role": "user", "content": text}
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_facts",
                    "description": "List stored facts",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_fact",
                    "description": "Store a fact",
                    "parameters": {
                        "type": "object",
                        "properties": {"fact": {"type": "string"}},
                        "required": ["fact"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_fact",
                    "description": "Delete a fact",
                    "parameters": {
                        "type": "object",
                        "properties": {"fact": {"type": "string"}},
                        "required": ["fact"],
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
                if call.function.name == "add_fact" and args.get("fact"):
                    result = await _add_fact(rds, uuid, args["fact"])
                elif call.function.name == "delete_fact" and args.get("fact"):
                    result = await _delete_fact(rds, uuid, args["fact"])
                elif call.function.name == "list_facts":
                    result = await _list_facts(rds, uuid)
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
        logger.exception("fact extraction failed")


async def _aggregate_facts(rds, uuid: str) -> Message | None:
    """Collect all stored facts and return as a single message."""
    facts = await rds.smembers(f"user:{uuid}:facts")
    if not facts:
        return None
    text = "; ".join(sorted(f.decode() if isinstance(f, bytes) else f for f in facts))
    return Message(role="user", content=text)


async def _list_facts(rds, uuid: str) -> list[str]:
    """Return sorted list of stored facts."""
    facts = await rds.smembers(f"user:{uuid}:facts")
    return sorted(f.decode() if isinstance(f, bytes) else f for f in facts)


async def _delete_fact(rds, uuid: str, fact: str) -> int:
    """Remove a fact for a user and return count removed."""
    return await rds.srem(f"user:{uuid}:facts", fact)


async def _add_fact(rds, uuid: str, fact: str) -> None:
    """Store a new fact for a user."""
    await rds.sadd(f"user:{uuid}:facts", fact)


__all__ = [
    "_check_and_store_fact",
    "_aggregate_facts",
    "_list_facts",
    "_delete_fact",
    "_add_fact",
]
