async def _ensure_company(uuid: str, company_id: str) -> None:
    from fastapi import HTTPException

    from app.main import app

    rds = app.state.redis
    stored = await rds.hget(f"user:{uuid}:data", "company_id")
    if isinstance(stored, bytes):
        stored = stored.decode()
    if stored != company_id:
        raise HTTPException(status_code=403, detail="forbidden")


async def _company_feature_enabled(
    company: str, feature: str, default: bool = True
) -> bool:
    from app.main import app

    rds = app.state.redis
    val = await rds.hget(f"company:{company}:data", feature)
    if val is None:
        return default
    if isinstance(val, bytes):
        val = val.decode()
    try:
        return bool(int(val))
    except Exception:
        return val.lower() in {"true", "yes"}


__all__ = ["_ensure_company", "_company_feature_enabled"]
