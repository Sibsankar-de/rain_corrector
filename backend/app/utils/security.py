"""Cryptographic helpers.

API keys are stored as keyed digests (HMAC-SHA256) using the server secret as
the pepper, so a database leak does not expose usable keys and verification
stays deterministic.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.core.config import settings


def hash_api_key(raw_key: str, pepper: str | None = None) -> str:
    secret = (pepper or settings.secret_key).encode()
    return hmac.new(secret, raw_key.encode(), hashlib.sha256).hexdigest()


def generate_api_key(prefix: str = "rck") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)
