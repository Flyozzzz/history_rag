import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.main import app
from app.models import DeleteFactRequest, DeleteFactResponse, FactsResponse
from app.services.company import _ensure_company
from app.services.facts import _delete_fact, _list_facts

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/facts", response_model=FactsResponse)
async def list_facts(
    uuid: str = Query(...),
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    facts = await _list_facts(rds, uuid)
    return {"uuid": uuid, "facts": facts}


@router.delete("/facts", response_model=DeleteFactResponse)
async def delete_fact(
    req: DeleteFactRequest,
    user: tuple[str, str] = Depends(get_current_user),
):
    uid, company = user
    if req.uuid != uid:
        raise HTTPException(status_code=403, detail="forbidden")
    await _ensure_company(uid, company)
    rds = app.state.redis
    removed = await _delete_fact(rds, req.uuid, req.fact)
    return {"uuid": req.uuid, "removed": removed}
