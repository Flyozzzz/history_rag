from typing import Any, Dict

from app.config import Settings, get_settings

__all__ = [
    "increment_messages",
    "increment_tokens",
    "get_usage",
    "get_user_usage",
    "calculate_cost",
    "calculate_user_cost",
]


async def increment_messages(
    rds, company_id: str, count: int = 1, user_id: str | None = None
) -> None:
    """Increment message usage counter."""
    await rds.incrby(f"company:{company_id}:usage:messages", count)
    if user_id:
        await rds.incrby(f"company:{company_id}:user:{user_id}:usage:messages", count)


async def increment_tokens(
    rds, company_id: str, count: int = 1, user_id: str | None = None
) -> None:
    """Increment token usage counter."""
    await rds.incrby(f"company:{company_id}:usage:tokens", count)
    if user_id:
        await rds.incrby(f"company:{company_id}:user:{user_id}:usage:tokens", count)


async def get_usage(rds, company_id: str) -> Dict[str, int]:
    """Return usage counters for a company."""
    msgs = await rds.get(f"company:{company_id}:usage:messages") or 0
    toks = await rds.get(f"company:{company_id}:usage:tokens") or 0
    msgs = int(msgs) if isinstance(msgs, (bytes, str)) else msgs
    toks = int(toks) if isinstance(toks, (bytes, str)) else toks
    return {"messages": msgs, "tokens": toks}


async def get_user_usage(rds, company_id: str, user_id: str) -> Dict[str, int]:
    """Return usage counters for a specific user."""
    msgs = await rds.get(f"company:{company_id}:user:{user_id}:usage:messages") or 0
    toks = await rds.get(f"company:{company_id}:user:{user_id}:usage:tokens") or 0
    msgs = int(msgs) if isinstance(msgs, (bytes, str)) else msgs
    toks = int(toks) if isinstance(toks, (bytes, str)) else toks
    return {"messages": msgs, "tokens": toks}


async def calculate_cost(
    rds, company_id: str, settings: Settings | None = None
) -> float:
    """Calculate total cost for a company based on usage and pricing."""
    settings = settings or get_settings()
    usage = await get_usage(rds, company_id)
    return (
        usage["messages"] * settings.cost_per_message
        + usage["tokens"] * settings.cost_per_token
    )


async def calculate_user_cost(
    rds, company_id: str, user_id: str, settings: Settings | None = None
) -> float:
    """Calculate cost for a specific user."""
    settings = settings or get_settings()
    usage = await get_user_usage(rds, company_id, user_id)
    return (
        usage["messages"] * settings.cost_per_message
        + usage["tokens"] * settings.cost_per_token
    )
