"""Хеширование паролей (passlib, PBKDF2) и подписанные токены (python-jose, HS256)."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from . import config

ALGORITHM = "HS256"

password_context = CryptContext(schemes=["pbkdf2_sha256"], pbkdf2_sha256__default_rounds=config.PASSWORD_HASH_ROUNDS)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_context.verify(password, stored_hash)
    except ValueError:  # хеш в неизвестном формате
        return False


def create_token(user_id: int, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_TTL_HOURS)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": expires}, config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Возвращает содержимое токена или None, если подпись неверна или срок истёк."""
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
