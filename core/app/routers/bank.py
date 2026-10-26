"""API сотрудников банка: очередь заявок, карточка со скорингом, ручные решения, аудит."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import statemachine as fsm
from ..db import get_db
from ..deps import actor, analyst_user
from ..errors import AppError
from ..models import Application, User
from ..schemas import CommentIn, DecisionIn, RejectIn
from ..serializers import bank_detail, bank_row
from ..services import apply_decision, display_status
from ..tasks import enqueue

router = APIRouter(prefix="/api/bank", tags=["bank"])

MAX_RATE = 60


def get_app(db: Session, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app or app.status == "DRAFT":  # черновики клиентов сотрудникам не видны
        raise AppError("Заявка не найдена", 404, "not_found")
    return app


def _decision_trigger(app: Application) -> str:
    for trigger in ("manual_decide", "override_decision"):
        if fsm.can(app.status, trigger):
            return trigger
    raise AppError(
        "По этой заявке сейчас нельзя принять решение",
        409,
        "invalid_transition",
        "Решение принимается, пока заявка на ручной проверке или после автоматического решения (до подписания)",
    )


def _check_limits(app: Application, amount: int, rate: float | None) -> None:
    product = app.product
    if product and not product.min_sum <= amount <= product.max_sum:
        message = (
            f"Сумма должна быть в пределах продукта «{product.name}»: от {product.min_sum:,} до {product.max_sum:,} ₽"
        )
        raise AppError(
            message.replace(",", " "),
            422,
            "bad_amount",
            fields=[{"field": "amount", "message": "Сумма вне лимитов продукта"}],
        )
    if rate is not None and not 0 < rate < MAX_RATE:
        raise AppError(
            f"Ставка должна быть от 0 до {MAX_RATE}% годовых",
            422,
            "bad_rate",
            fields=[{"field": "rate", "message": "Некорректная ставка"}],
        )


def _offer_terms(app: Application, body: DecisionIn) -> tuple[int, float | None]:
    """Условия из запроса аналитика; недостающее берётся из заявки и продукта."""
    amount = body.amount or app.requested_amount
    rate = body.rate or (app.product.base_rate if app.product else None)
    _check_limits(app, amount, rate)
    return amount, rate


def _submitted_applications(db: Session) -> list[Application]:
    return [app for app in db.scalars(select(Application).order_by(Application.id)) if app.status != "DRAFT"]


@router.get("/stats", summary="Дашборд: карточки статистики")
def stats(user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    apps = _submitted_applications(db)
    labels = [display_status(app)["label"] for app in apps]
    scores = [app.scorings[-1].risk_score for app in apps if app.scorings]
    return {
        "total": len(apps),
        "review": labels.count("На проверке"),
        "docs_requested": labels.count("Нужны документы"),
        "approved": labels.count("Одобрена"),
        "rejected": labels.count("Отказ"),
        "manual_queue": sum(1 for app in apps if app.status == "MANUAL_REVIEW"),
        "avg_score": round(sum(scores) / len(scores)) if scores else None,
    }


@router.get("/applications", summary="Очередь заявок (фильтр status по подписи или коду статуса, поиск q)")
def queue(
    status: str | None = None,
    q: str | None = None,
    user: User = Depends(analyst_user),
    db: Session = Depends(get_db),
):
    apps = _submitted_applications(db)
    if status:
        apps = [app for app in apps if status in (app.status, display_status(app)["label"])]
    if q:
        query = q.lower()
        apps = [
            app
            for app in apps
            if query in (app.number or "").lower()
            or (app.company and (query in app.company.name.lower() or query in app.company.inn))
        ]
    return [bank_row(app) for app in apps]


@router.get("/applications/{app_id}", summary="Карточка заявки: данные, скоринг с факторами, ответы ФНС и БКИ, история")
def detail(app_id: int, user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    return bank_detail(get_app(db, app_id))


@router.get("/applications/{app_id}/history", summary="Аудит: все изменения статуса и ручные действия")
def audit(app_id: int, user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    return bank_detail(get_app(db, app_id))["history"]


@router.post("/applications/{app_id}/approve", summary="Одобрить вручную")
def approve(
    app_id: int, body: DecisionIn | None = None, user: User = Depends(analyst_user), db: Session = Depends(get_db)
):
    body, app = body or DecisionIn(), get_app(db, app_id)
    trigger = _decision_trigger(app)
    amount, rate = _offer_terms(app, body)
    decision = {"decision": "APPROVED", "amount": amount, "rate": rate, "reason": body.comment or "Одобрено аналитиком"}
    apply_decision(db, app, decision, actor(user), "MANUAL", trigger)
    db.commit()
    return bank_detail(app)


@router.post(
    "/applications/{app_id}/counter-offer", summary="Предложить другие условия (меньшая сумма или другая ставка)"
)
def counter(app_id: int, body: DecisionIn, user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    app = get_app(db, app_id)
    trigger = _decision_trigger(app)
    if not body.amount and not body.rate:
        raise AppError(
            "Укажите новую сумму или ставку для встречного предложения",
            422,
            "empty_offer",
            fields=[{"field": "amount", "message": "Укажите сумму или ставку"}],
        )
    amount, rate = _offer_terms(app, body)
    decision = {
        "decision": "COUNTER_OFFER",
        "amount": amount,
        "rate": rate,
        "reason": body.comment or "Встречное предложение аналитика",
    }
    apply_decision(db, app, decision, actor(user), "MANUAL", trigger)
    db.commit()
    return bank_detail(app)


@router.post("/applications/{app_id}/reject", summary="Отказать (причина обязательна и показывается клиенту)")
def reject(app_id: int, body: RejectIn, user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    app = get_app(db, app_id)
    decision = {"decision": "REJECTED", "amount": None, "rate": None, "reason": body.reason}
    apply_decision(db, app, decision, actor(user), "MANUAL", _decision_trigger(app))
    db.commit()
    return bank_detail(app)


@router.post("/applications/{app_id}/request-documents", summary="Запросить дополнительные документы у клиента")
def request_documents(app_id: int, body: CommentIn, user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    app = get_app(db, app_id)
    fsm.fire(db, app, "request_documents", actor(user), body.comment)
    db.commit()
    return bank_detail(app)


@router.post(
    "/applications/{app_id}/rerun-scoring", summary="Пересчитать скоринг (данные ФНС и БКИ запрашиваются заново)"
)
def rerun(app_id: int, background: BackgroundTasks, user: User = Depends(analyst_user), db: Session = Depends(get_db)):
    app = get_app(db, app_id)
    fsm.fire(db, app, "rerun", actor(user), "Аналитик запустил повторный скоринг")
    app.decision = app.decision_by = app.decision_reason = app.approved_amount = app.approved_rate = None
    db.commit()
    enqueue(app.id, background)
    return bank_detail(app)
