from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import AppError
from .models import Application, ApplicationStateHistory, Company, CreditProduct, User


def new_number(db: Session) -> str:
    year = datetime.now().year
    prefix = f"КР-{year}-"
    nums = [
        int(n.split("-")[-1])
        for (n,) in db.execute(select(Application.number).where(Application.number.like(prefix + "%")))
        if n
    ]
    return f"{prefix}{(max(nums) + 1 if nums else 1):04d}"


def upsert_company(db: Session, inn: str | None, name: str | None) -> Company | None:
    if not inn:
        return None
    c = db.scalar(select(Company).where(Company.inn == inn))
    if not c:
        c = Company(inn=inn, name=name or f"Компания {inn}", financial_metrics={})
        db.add(c)
        db.flush()
    elif name and c.name != name and c.name.startswith("Компания "):
        c.name = name
    return c


def create_application(db: Session, user: User, data: dict, actor: str, number: str | None = None) -> Application:
    company = upsert_company(db, data.get("inn"), data.get("company_name"))
    app = Application(
        number=number or new_number(db),
        user_id=user.id,
        company_id=company.id if company else None,
        product_id=data.get("product_id"),
        requested_amount=data.get("requested_amount"),
        term_months=data.get("term_months"),
        purpose=data.get("purpose"),
        status="DRAFT",
    )
    db.add(app)
    db.flush()
    db.add(
        ApplicationStateHistory(
            application_id=app.id, from_status=None, to_status="DRAFT", actor=actor, comment="Заявка создана"
        )
    )
    return app


def get_product(db: Session, product_id: int | None) -> CreditProduct | None:
    if product_id is None:
        return None
    p = db.get(CreditProduct, product_id)
    if not p:
        raise AppError(
            "Такого кредитного продукта нет",
            422,
            "bad_product",
            "Выберите продукт из списка на странице «Подобрать кредит»",
            fields=[{"field": "product_id", "message": "Выберите кредитный продукт из списка"}],
        )
    return p


def app_to_form(app: Application) -> dict:
    return {
        "product_id": app.product_id,
        "requested_amount": app.requested_amount,
        "term_months": app.term_months,
        "purpose": app.purpose,
        "inn": app.company.inn if app.company else None,
        "company_name": app.company.name if app.company else None,
    }


def all_products(db: Session) -> list[CreditProduct]:
    return list(db.scalars(select(CreditProduct).order_by(CreditProduct.id)))
