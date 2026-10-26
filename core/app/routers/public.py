"""Общедоступные и общие для ролей методы: вход, профиль, продукты, поиск компании, ИИ-ассистент."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai, enrichment
from ..crud import get_product, upsert_company
from ..db import get_db
from ..deps import current_user
from ..errors import AppError
from ..models import Company, CreditProduct, User
from ..schemas import AssistantIn, LoginIn, RegisterIn
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api")


def product_out(p: CreditProduct):
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "purpose": p.purpose,
        "base_rate": p.base_rate,
        "min_sum": p.min_sum,
        "max_sum": p.max_sum,
        "min_term": p.min_term,
        "max_term": p.max_term,
    }


@router.post("/auth/login", tags=["auth"], summary="Вход. Возвращает Bearer-токен")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise AppError(
            "Неверный email или пароль", 401, "bad_credentials", "Проверьте раскладку клавиатуры и Caps Lock"
        )
    return {"token": create_token(user.id, user.role), "role": user.role, "full_name": user.full_name}


@router.post("/auth/register", status_code=201, tags=["auth"], summary="Регистрация клиента. Возвращает Bearer-токен")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise AppError(
            "Пользователь с таким email уже зарегистрирован",
            409,
            "email_taken",
            "Войдите в кабинет или укажите другой адрес",
            [{"field": "email", "message": "Этот email уже занят"}],
        )
    company = upsert_company(db, body.inn, body.company_name)
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
        role="client",
        company_id=company.id if company else None,
    )
    db.add(user)
    db.commit()
    return {"token": create_token(user.id, user.role), "role": user.role, "full_name": user.full_name}


@router.get("/me", tags=["auth"], summary="Профиль текущего пользователя")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id) if user.company_id else None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "company": None if not company else {"id": company.id, "name": company.name, "inn": company.inn},
    }


@router.get("/products", tags=["products"], summary="Каталог кредитных продуктов")
def products(db: Session = Depends(get_db)):
    return [product_out(p) for p in db.scalars(select(CreditProduct).order_by(CreditProduct.id))]


@router.get("/products/{product_id}", tags=["products"])
def product(product_id: int, db: Session = Depends(get_db)):
    return product_out(get_product(db, product_id))


@router.get(
    "/companies/lookup/{inn}", tags=["companies"], summary="Название и данные компании по ИНН (автозаполнение мастера)"
)
def lookup(inn: str, user: User = Depends(current_user)):
    try:
        fns = enrichment.fetch_fns(inn)
    except Exception:
        raise AppError(
            "Не удалось найти компанию по этому ИНН",
            404,
            "company_not_found",
            "Проверьте номер или введите название вручную - заявку всё равно можно отправить",
        )
    return {
        "inn": inn,
        "name": fns["name"],
        "ogrn": fns["ogrn"],
        "industry_code": fns["industry_code"],
        "registration_date": fns["registration_date"],
    }


@router.post(
    "/ai/assistant", tags=["ai"], summary="ИИ-ассистент: по фразе клиента подбирает продукт и предзаполняет заявку"
)
def assistant(body: AssistantIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ai.assistant(body.message, list(db.scalars(select(CreditProduct))))
