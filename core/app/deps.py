from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .errors import AppError
from .models import User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    data = decode_token(cred.credentials) if cred else None
    user = db.get(User, int(data["sub"])) if data else None
    if not user:
        raise AppError("Нужно войти в кабинет", 401, "unauthorized", "Войдите заново - срок сессии мог истечь")
    return user


def client_user(user: User = Depends(current_user)) -> User:
    if user.role != "client":
        raise AppError("Этот раздел доступен только клиентам банка", 403, "forbidden")
    return user


def analyst_user(user: User = Depends(current_user)) -> User:
    if user.role != "analyst":
        raise AppError("Этот раздел доступен только сотрудникам банка", 403, "forbidden")
    return user


def actor(user: User) -> str:
    return f"{user.role}:{user.email}"
