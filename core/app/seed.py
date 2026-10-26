"""Демо-данные: пользователи, продукты, компании и три заявки из макета фронта.

Заявки проходят через настоящий конвейер, а не вставляются готовыми.
Повторный запуск ничего не дублирует.
"""

import logging

from sqlalchemy import select

from . import statemachine as fsm
from .crud import create_application, upsert_company
from .db import SessionLocal, run_migrations
from .models import Application, CreditProduct, Document, User
from .security import hash_password
from .services import run_pipeline

log = logging.getLogger("seed")

PRODUCTS = [
    dict(
        name="Бизнес-старт",
        base_rate=12.5,
        min_sum=100_000,
        max_sum=5_000_000,
        min_term=6,
        max_term=36,
        purpose="Развитие бизнеса",
        description="Финансирование для запуска новых направлений и развития компании.",
        risk_rules={"max_risk_level": "MEDIUM"},
    ),
    dict(
        name="Оборотный",
        base_rate=13.2,
        min_sum=100_000,
        max_sum=15_000_000,
        min_term=3,
        max_term=24,
        purpose="Пополнение оборотных средств",
        description="Пополнение оборотных средств и покрытие текущих расходов.",
        risk_rules={"max_risk_level": "MEDIUM"},
    ),
    dict(
        name="На оборудование",
        base_rate=14.1,
        min_sum=100_000,
        max_sum=10_000_000,
        min_term=12,
        max_term=60,
        purpose="Покупка оборудования",
        description="Покупка оборудования для расширения производства или услуг.",
        risk_rules={"max_risk_level": "MEDIUM"},
    ),
]
COMPANIES = [
    ("7812345678", "ООО «Север»"),
    ("781234567890", "ИП Иванов"),
    ("7801122334", "ООО «Вектор»"),
    ("7700000001", "ООО «Кедр-Трейд»"),
    ("7700000002", "ООО «Фортуна Гейминг»"),
]
# номер, ИНН, продукт, сумма, срок, цель
DEMO_APPS = [
    ("КР-2026-0148", "7812345678", "Оборотный", 3_000_000, 24, "Пополнение оборотных средств"),
    ("КР-2026-0149", "781234567890", "Оборотный", 1_500_000, 12, "Пополнение оборотных средств"),
    ("КР-2026-0150", "7801122334", "На оборудование", 5_000_000, 36, "Покупка оборудования"),
]
DEMO_DOCS = {
    "КР-2026-0148": [("BALANCE", "Бухгалтерская отчётность.pdf"), ("STATEMENT", "Выписка по счёту.pdf")],
    "КР-2026-0150": [("INVOICE", "Счёт на оборудование.pdf")],
}


def seed(run_pipelines: bool = True) -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(User).limit(1)):
            return
        for p in PRODUCTS:
            db.add(CreditProduct(**p))
        for inn, name in COMPANIES:
            upsert_company(db, inn, name)
        db.flush()
        sever = upsert_company(db, "7812345678", None)
        anna = User(
            email="anna@example.test",
            password_hash=hash_password("demo123"),
            full_name="Анна Андреева",
            role="client",
            company_id=sever.id,
        )
        analyst = User(
            email="analyst@bank.test", password_hash=hash_password("demo123"), full_name="Пётр Кредитов", role="analyst"
        )
        db.add_all([anna, analyst])
        db.flush()
        prod = {p.name: p.id for p in db.scalars(select(CreditProduct))}
        for number, inn, pname, amount, term, purpose in DEMO_APPS:
            app = create_application(
                db,
                anna,
                dict(inn=inn, product_id=prod[pname], requested_amount=amount, term_months=term, purpose=purpose),
                "client:anna@example.test",
                number,
            )
            for dtype, fname in DEMO_DOCS.get(number, []):
                db.add(Document(application_id=app.id, type=dtype, filename=fname, file_path=None))
            fsm.fire(db, app, "submit", "client:anna@example.test", "Клиент отправил заявку")
        db.commit()
        ids = [a.id for a in db.scalars(select(Application).order_by(Application.id))]
    finally:
        db.close()
    if run_pipelines:
        for i in ids:
            run_pipeline(i)
        # По заявке ИП Иванова аналитик запрашивает документы: так на демо появляется статус «Нужны документы».
        db = SessionLocal()
        try:
            a = db.scalar(select(Application).where(Application.number == "КР-2026-0149"))
            if a.status == "MANUAL_REVIEW":
                fsm.fire(
                    db,
                    a,
                    "request_documents",
                    "analyst:analyst@bank.test",
                    "Приложите, пожалуйста, актуальную бухгалтерскую отчётность и выписку по счёту за 6 месяцев",
                )
                db.commit()
        finally:
            db.close()
    log.info("seed done")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    seed()
