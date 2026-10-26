"""Хеширование паролей (PBKDF2) и подписанные токены (HS256) на стандартной библиотеке."""

import base64
import hashlib
import hmac
import json
import os
import time

from . import config


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$")
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)
    except ValueError:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: int, role: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps({"sub": user_id, "role": role, "exp": int(time.time()) + config.TOKEN_TTL_HOURS * 3600}).encode()
    )
    sig = _b64(hmac.new(config.SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        header, payload, sig = token.split(".")
        expected = _b64(hmac.new(config.SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        return data if data["exp"] > time.time() else None
    except Exception:
        return None
