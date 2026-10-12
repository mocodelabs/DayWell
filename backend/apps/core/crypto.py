"""Symmetric encryption for small secrets stored in the database (Web Push endpoints/keys).

The key comes from FIELD_ENCRYPTION_KEYS (comma-separated Fernet keys, newest first — supports rotation), or is
derived from SECRET_KEY when unset (development). See docs/DEPLOYMENT.md "Secret rotation".
"""

from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    raw = os.environ.get("FIELD_ENCRYPTION_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        derived = base64.urlsafe_b64encode(hashlib.sha256(f"daywell-field-key:{settings.SECRET_KEY}".encode()).digest())
        keys = [derived.decode()]
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt stored secret (encryption key changed?).") from exc


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
