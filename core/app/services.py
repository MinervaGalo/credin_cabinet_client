"""Кредитный конвейер: от отправленной заявки до решения или передачи аналитику."""

import logging

from sqlalchemy.orm import Session

from . import ai, enrichment
from . import statemachine as fsm
from .db import SessionLocal
from .decision import decide
from .models import Application, EnrichmentData, ScoringResult
from .scoring import score_application

log = logging.getLogger("pipeline")

# Статус заявки -> (подпись для клиента, css-класс из styles.css, шаг индикатора прогресса от 1 до 5).
DISPLAY = {
    "DRAFT": ("Черновик", "draft", 1),
    "SUBMITTED": ("На проверке", "review", 4),
    "DATA_ENRICHMENT": ("На проверке", "review", 4),
    "SCORING": ("На проверке", "review", 4),
    "MANUAL_REVIEW": ("На проверке", "review", 4),
    "DOCUMENTS_REQUESTED": ("Нужны документы", "docs", 3),
    "AWAITING_SIGNING": ("Одобрена", "approved", 5),
    "DISBURSED": ("Одобрена", "approved", 5),
}


def display_status(app: Application) -> dict:
    if app.status == "DECISION_MADE":
        label, css = {"REJECTED": ("Отказ", "rejected")}.get(app.decision, ("Одобрена", "approved"))
        return {"label": label, "css": css, "step": 5}
    label, css, step = DISPLAY[app.status]
    return {"label": label, "css": css, "step": step}


def apply_decision(
    db: Session, app: Application, decision: dict, actor: str, decided_by: str, trigger: str = "decide"
) -> None:
    app.decision, app.decision_by, app.decision_reason = decision["decision"], decided_by, decision["reason"]
    app.approved_amount, app.approved_rate = decision.get("amount"), decision.get("rate")
    fsm.fire(db, app, trigger, actor, f"{decision['decision']}: {decision['reason']}")


def _enrich(db: Session, app: Application) -> tuple[dict, dict]:
    inn = app.company.inn
    fns, bki = enrichment.fetch_fns(inn), enrichment.fetch_bki(inn)
    db.add_all(
        [
            EnrichmentData(application_id=app.id, source="FNS", payload_json=fns),
            EnrichmentData(application_id=app.id, source="BKI", payload_json=bki),
        ]
    )
    company = app.company
    company.ogrn, company.industry_code, company.registration_date = (
        fns["ogrn"],
        fns["industry_code"],
        fns["registration_date"],
    )
    company.financial_metrics = {
        **(company.financial_metrics or {}),
        "revenue_monthly_avg": fns["revenue_monthly_avg"],
        "revenue_last_12m": fns["revenue_last_12m"],
        "net_profit": fns["net_profit_last_year"],
    }
    return fns, bki


def _score_and_decide(db: Session, app: Application, fns: dict, bki: dict) -> None:
    scoring = score_application(app.requested_amount, fns, bki)
    decision = decide(
        scoring["risk_level"],
        scoring["risk_score"],
        app.requested_amount,
        app.term_months,
        app.product,
        scoring["hard_stop"],
    )
    summary = ai.explain(scoring["risk_score"], scoring["risk_level"], scoring["factors"], decision["decision"])
    db.add(
        ScoringResult(
            application_id=app.id,
            risk_score=scoring["risk_score"],
            risk_level=scoring["risk_level"],
            factors_json=scoring["factors"],
            summary=summary,
        )
    )
    if decision["next"] == "decide":
        apply_decision(db, app, decision, "system", "AUTO")
    else:
        fsm.fire(db, app, "send_to_review", "system", decision["reason"])


def run_pipeline(application_id: int) -> None:
    """Обрабатывает заявку в фоне. Повторный вызов для уже обработанной заявки ничего не делает."""
    db = SessionLocal()
    try:
        app = db.get(Application, application_id)
        if not app or app.status != "SUBMITTED":
            return

        fsm.fire(db, app, "start_enrichment", "system", "Запрашиваем данные ФНС и БКИ")
        db.commit()

        try:
            fns, bki = _enrich(db, app)
        except Exception as error:
            # Заявку нельзя терять из-за сбоя внешнего сервиса: передаём её аналитику.
            log.warning("enrichment failed for %s: %s", app.number, error)
            fsm.fire(db, app, "send_to_review", "system", "Внешние сервисы (ФНС/БКИ) недоступны, нужна ручная проверка")
            db.commit()
            return

        fsm.fire(db, app, "start_scoring", "system", "Данные получены, считаем скоринг")
        db.commit()

        _score_and_decide(db, app, fns, bki)
        db.commit()
    except Exception:
        log.exception("pipeline crashed for application %s", application_id)
        db.rollback()
    finally:
        db.close()
