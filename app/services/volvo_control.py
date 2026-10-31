"""Cloud Volvo sync pause/resume: persisted in Neon, cached in one web worker.

A paused collector does not query Neon every 5 minutes just to check whether
it should remain paused. The management API updates both persisted and cached
state. Restart reloads the flag from Neon once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from sqlalchemy.orm import Session
from app.volvo_models import VolvoSyncControl

_enabled: bool | None = None
_guard = Lock()


def collection_enabled(db: Session) -> bool:
    global _enabled
    if _enabled is None:
        with _guard:
            if _enabled is None:
                row = db.get(VolvoSyncControl, 1)
                _enabled = bool(row.enabled) if row else True
    return bool(_enabled)


def set_collection_enabled(db: Session, enabled: bool, actor: str) -> bool:
    global _enabled
    row = db.get(VolvoSyncControl, 1)
    if row is None:
        row = VolvoSyncControl(id=1, enabled=bool(enabled))
        db.add(row)
    row.enabled = bool(enabled)
    row.changed_by = (actor or "ADMIN")[:60]
    row.changed_at = datetime.now(timezone.utc)
    db.commit()
    with _guard:
        _enabled = bool(enabled)
    return bool(enabled)
