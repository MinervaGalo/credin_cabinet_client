"""Конечный автомат статусов заявки на библиотеке `transitions`.

Статусы взяты из ТЗ; DOCUMENTS_REQUESTED добавлен, чтобы хранить запрос документов
из кабинета банка. Каждый переход попадает в аудит, недопустимый возвращает ошибку 409.
"""

from sqlalchemy.orm import Session
from transitions import Machine, MachineError

from .errors import AppError
from .models import Application, ApplicationStateHistory

STATES = [
    "DRAFT",
    "SUBMITTED",
    "DATA_ENRICHMENT",
    "SCORING",
    "MANUAL_REVIEW",
    "DOCUMENTS_REQUESTED",
    "DECISION_MADE",
    "AWAITING_SIGNING",
    "DISBURSED",
]

TRANSITIONS = [
    ("submit", "DRAFT", "SUBMITTED"),
    ("start_enrichment", "SUBMITTED", "DATA_ENRICHMENT"),
    ("start_scoring", "DATA_ENRICHMENT", "SCORING"),
    ("decide", "SCORING", "DECISION_MADE"),
    ("send_to_review", ["SCORING", "DATA_ENRICHMENT"], "MANUAL_REVIEW"),
    ("request_documents", "MANUAL_REVIEW", "DOCUMENTS_REQUESTED"),
    ("documents_provided", "DOCUMENTS_REQUESTED", "MANUAL_REVIEW"),
    ("manual_decide", "MANUAL_REVIEW", "DECISION_MADE"),
    ("override_decision", "DECISION_MADE", "DECISION_MADE"),
    ("rerun", ["MANUAL_REVIEW", "DECISION_MADE"], "SUBMITTED"),
    ("accept_offer", "DECISION_MADE", "AWAITING_SIGNING"),
    ("sign", "AWAITING_SIGNING", "DISBURSED"),
]

TRIGGER_HINTS = {
    "submit": "Заявка уже отправлена в банк",
    "request_documents": "Запросить документы можно, пока заявка на ручной проверке",
    "manual_decide": "Принять решение вручную можно, пока заявка на ручной проверке",
    "override_decision": "Изменить решение можно после автоматического решения и до подписания",
    "accept_offer": "Принять предложение можно только по одобренной заявке",
    "sign": "Подписать можно только заявку, которая ожидает подписания",
    "documents_provided": "Банк не запрашивал документы по этой заявке",
}


class _Model:
    """Объект для `transitions`: хранит только текущий статус."""

    def __init__(self, state: str):
        self.state = state


def _machine(state: str):
    m = _Model(state)
    machine = Machine(model=m, states=STATES, initial=state, auto_transitions=False, send_event=False)
    for trig, src, dst in TRANSITIONS:
        machine.add_transition(trig, src, dst)
    return m, machine


def can(status: str, trigger: str) -> bool:
    m, _ = _machine(status)
    return getattr(m, f"may_{trigger}")()


def fire(db: Session, app: Application, trigger: str, actor: str, comment: str | None = None) -> str:
    """Выполнить переход, записать аудит. Коммит - на вызывающем."""
    m, _ = _machine(app.status)
    try:
        getattr(m, trigger)()
    except MachineError:
        raise AppError(
            "Сейчас это действие недоступно для заявки",
            status=409,
            code="invalid_transition",
            hint=TRIGGER_HINTS.get(trigger, f"Текущий статус заявки: {app.status}"),
        )
    db.add(
        ApplicationStateHistory(
            application_id=app.id, from_status=app.status, to_status=m.state, actor=actor, comment=comment
        )
    )
    app.status = m.state
    return m.state
