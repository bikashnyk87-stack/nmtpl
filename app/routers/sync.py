from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import csrf, get_user, require
from app.db import get_db
from app.services.cloud_sync import (
    create_device,
    latest_change_id,
    read_changes,
    source_enabled,
    validate_device,
)

router = APIRouter(prefix="/api/sync", tags=["sync"])


class PairIn(BaseModel):
    deviceName: str = Field(default="NMTPL Base PC", min_length=1, max_length=120)


def _source_required() -> None:
    if not source_enabled():
        raise HTTPException(503, "Render-to-PC sync source is not enabled.")


@router.get("/status")
def status(db: Session = Depends(get_db)):
    if not source_enabled():
        return {"enabled": False}
    return {"enabled": True, "latestChangeId": latest_change_id(db)}


@router.post("/pair")
def pair_device(p: PairIn, request: Request, db: Session = Depends(get_db)):
    _source_required()
    csrf(request)
    user = get_user(db, request)
    require(user, admin=True)
    paired = create_device(db, p.deviceName)
    return {"ok": True, **paired, "startAfterChangeId": 0}


@router.get("/changes")
def changes(
    after: int = 0,
    limit: int = 500,
    x_nmtpl_sync_token: str | None = Header(default=None, alias="X-NMTPL-Sync-Token"),
    db: Session = Depends(get_db),
):
    _source_required()
    device = validate_device(db, x_nmtpl_sync_token or "")
    if not device:
        raise HTTPException(401, "Invalid or inactive sync device token.")
    return read_changes(db, after, limit)
