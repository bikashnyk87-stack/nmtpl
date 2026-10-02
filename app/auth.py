"""Database-backed sessions for the local pilot webapp."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Integer, select
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

COOKIE = 'nmtpl_session'
MODULES = {'DASHBOARD', 'PERSON_ATTENDANCE', 'EQUIPMENT_ATTENDANCE', 'SHIFT_CONTROL', 'PRODUCTION', 'WB', 'HSD', 'MASTERS'}


class WebUser(Base):
    __tablename__ = 'web_user'
    login_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    modules: Mapped[str] = mapped_column(String(200), default='')
    shifts: Mapped[str] = mapped_column(String(100), default='ALL')
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebSession(Base):
    __tablename__ = 'web_session'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    login_id: Mapped[str] = mapped_column(ForeignKey('web_user.login_id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def hash_password(password):
    if not 12 <= len(password) <= 128:
        raise HTTPException(422, 'Use a password of 12–128 characters.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def check_password(password, stored):
    try:
        _, salt, expected = stored.split('$')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def digest_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def get_user(db, request):
    token = request.cookies.get(COOKIE, '')
    session = db.get(WebSession, digest_token(token)) if token else None
    if not session or aware(session.expires_at) <= utcnow():
        raise HTTPException(401, 'SESSION_EXPIRED: Please sign in.')
    user = db.get(WebUser, session.login_id)
    if not user or not user.active:
        raise HTTPException(401, 'SESSION_EXPIRED: Account is inactive.')
    return user


def csrf(request: Request):
    if request.headers.get('X-NMTPL-Request') != 'webapp':
        raise HTTPException(403, 'Use the NMTPL webapp to submit this request.')
    origin = request.headers.get('origin')
    if not origin:
        return
    # Reverse-proxy aware CSRF check for Cloudflare Tunnel.
    from urllib.parse import urlsplit
    try:
        origin_url = urlsplit(origin)
    except ValueError:
        raise HTTPException(403, 'Cross-origin requests are not permitted.')
    public_host = (request.headers.get('x-forwarded-host') or request.headers.get('host') or '').split(',')[0].strip().lower()
    origin_host = origin_url.netloc.lower()
    if origin_url.scheme not in {'http', 'https'} or not public_host or origin_host != public_host:
        raise HTTPException(403, 'Cross-origin requests are not permitted.')

def require(user, module=None, shift=None, admin=False):
    if admin and not user.admin:
        raise HTTPException(403, 'Management access required.')
    if module and not user.admin and module not in user.modules.split(','):
        raise HTTPException(403, 'This module is not assigned to your account.')
    if shift and not user.admin and 'ALL' not in user.shifts.split(',') and shift not in user.shifts.split(','):
        raise HTTPException(403, 'This shift is not assigned to your account.')


def issue_session(db, user, response, request):
    token = secrets.token_urlsafe(32)
    db.add(WebSession(token_hash=digest_token(token), login_id=user.login_id,
                      expires_at=utcnow() + timedelta(hours=12)))
    response.set_cookie(COOKIE, token, max_age=43200, httponly=True, samesite='strict',
                        secure=(request.url.scheme == 'https' or request.headers.get('x-forwarded-proto', '').split(',')[0].strip() == 'https'), path='/')
