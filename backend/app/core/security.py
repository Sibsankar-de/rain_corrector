"""Application-wide security dependencies.

API key auth is optional (disabled by default in development) so the frontend
can be run without credentials. When enabled, every data route requires a key
except health and documentation endpoints.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.models.user import APIKey, User
from app.utils.security import hash_api_key


def _extract_key(request: Request) -> str | None:
    header = request.headers.get(settings.api_key_header)
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def require_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    if not settings.enable_api_key_auth:
        return await _system_user(db)

    raw_key = _extract_key(request)
    if not raw_key:
        raise AuthenticationError("An API key header is required.")

    digest = hash_api_key(raw_key)
    record = await db.scalar(select(APIKey).where(APIKey.key_hash == digest))
    if record is None or not record.is_active:
        raise AuthenticationError("The supplied API key is invalid.")

    now = datetime.now(UTC)
    if record.expires_at is not None and record.expires_at < now:
        raise AuthenticationError("The supplied API key has expired.")

    user = await db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("The account linked to this key is inactive.")

    record.last_used_at = now
    await db.commit()
    return user


async def _system_user(db: AsyncSession) -> User:
    """Return (creating if needed) the non-human actor used in dev mode."""
    user = await db.scalar(select(User).where(User.username == "system"))
    if user is None:
        user = User(
            username="system", email="system@localhost", is_active=True, is_service_account=True
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).hexdigest(), hashlib.sha256(right.encode()).hexdigest()
    )
