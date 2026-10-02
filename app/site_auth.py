from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from app.site_models import UserPermission, UserSiteAccess


def accessible_sites(db, user) -> set[str]:
    if user.admin:
        return {"TIOM", "SOCP", "KOCP"}
    return set(db.scalars(
        select(UserSiteAccess.site_id).where(
            UserSiteAccess.login_id == user.login_id,
            UserSiteAccess.active.is_(True),
        )
    ))


def require_site(db, user, site_id: str) -> str:
    site_id = str(site_id or "").upper().strip()
    if not site_id:
        raise HTTPException(422, "Site is required.")
    if user.admin:
        return site_id
    if site_id not in accessible_sites(db, user):
        raise HTTPException(403, "This site is not assigned to your account.")
    return site_id


def has_permission(db, user, site_id: str, module: str, action: str) -> bool:
    if user.admin:
        return True
    site_id = site_id.upper()
    module = module.upper()
    action = action.upper()
    candidates = {
        f"{site_id}.{module}.{action}",
        f"{site_id}.{module}.ALL",
        f"{site_id}.*.{action}",
        f"{site_id}.*.ALL",
        f"*.{module}.{action}",
        f"*.{module}.ALL",
        "*.*.ALL",
    }
    found = db.scalar(select(UserPermission.id).where(
        UserPermission.login_id == user.login_id,
        UserPermission.active.is_(True),
        UserPermission.permission.in_(candidates),
    ).limit(1))
    return found is not None


def require_permission(db, user, site_id: str, module: str, action: str) -> None:
    site_id = require_site(db, user, site_id)
    if not has_permission(db, user, site_id, module, action):
        raise HTTPException(403, f"{module} {action.lower()} permission is required for {site_id}.")
