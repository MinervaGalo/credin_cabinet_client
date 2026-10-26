"""Преобразование моделей в JSON для фронта. Поле display.css совпадает с классами из styles.css."""

from . import statemachine as fsm
from .models import Application, Document
from .services import display_status

_RISK_RU = {"LOW": "Низкий", "MEDIUM": "Средний", "HIGH": "Высокий"}
_DOC_TYPES = {
    "BALANCE": "Бухгалтерская отчётность",
    "STATEMENT": "Выписка по счёту",
    "INVOICE": "Счёт",
    "OTHER": "Документ",
}


def iso(dt):
    return dt.isoformat() if dt else None


def company_out(c):
    return (
        None
        if not c
        else {
            "id": c.id,
            "name": c.name,
            "inn": c.inn,
            "ogrn": c.ogrn,
            "industry_code": c.industry_code,
            "registration_date": c.registration_date,
            "financial_metrics": c.financial_metrics or {},
        }
    )


def document_out(d: Document, app: Application | None = None):
    return {
        "id": d.id,
        "application_id": d.application_id,
        "type": d.type,
        "type_label": _DOC_TYPES.get(d.type, d.type),
        "filename": d.filename,
        "has_file": bool(d.file_path),
        "parsed_data": d.parsed_data_json,
        "uploaded_at": iso(d.uploaded_at),
        "application_number": app.number if app else None,
        "company_name": app.company.name if app and app.company else None,
    }


def timeline(app: Application) -> list[dict]:
    """Шаги для блока «История заявки»."""
    reached = {h.to_status for h in app.history}
    items = [{"title": "Заявка создана", "state": "done"}]
    if "SUBMITTED" in reached:
        items.append({"title": "Заявка отправлена в банк", "state": "done"})
    if "SCORING" in reached:
        items.append({"title": "Данные компании проверены", "state": "done"})
    if app.documents:
        items.append({"title": "Документы получены", "state": "done"})
    last = {
        "DRAFT": "Черновик, отправьте заявку в банк",
        "SUBMITTED": "Заявка принята, начинаем проверку",
        "DATA_ENRICHMENT": "Проверяем данные компании",
        "SCORING": "Оцениваем заявку",
        "MANUAL_REVIEW": "Заявка на рассмотрении у аналитика",
        "DOCUMENTS_REQUESTED": "Банк запросил документы",
        "AWAITING_SIGNING": "Ожидает подписания договора",
        "DISBURSED": "Деньги выданы",
        "DECISION_MADE": {"REJECTED": "Принято решение: отказ", "COUNTER_OFFER": "Банк предложил другие условия"}.get(
            app.decision, "Заявка одобрена"
        ),
    }[app.status]
    items.append({"title": last, "state": "done" if app.status == "DISBURSED" else "current"})
    return items


def application_out(app: Application, validation: dict | None = None) -> dict:
    disp = display_status(app)
    docs_req = (
        next((h.comment for h in reversed(app.history) if h.to_status == "DOCUMENTS_REQUESTED"), None)
        if app.status == "DOCUMENTS_REQUESTED"
        else None
    )
    return {
        "id": app.id,
        "number": app.number,
        "status": app.status,
        "display": disp,
        "company": company_out(app.company),
        "product": (
            None
            if not app.product
            else {"id": app.product.id, "name": app.product.name, "base_rate": app.product.base_rate}
        ),
        "requested_amount": app.requested_amount,
        "term_months": app.term_months,
        "purpose": app.purpose,
        "decision": app.decision,
        "decision_reason": app.decision_reason,
        "approved_amount": app.approved_amount,
        "approved_rate": app.approved_rate,
        "documents_request_comment": docs_req,
        "created_at": iso(app.created_at),
        "updated_at": iso(app.updated_at),
        "actions": {
            "submit": fsm.can(app.status, "submit"),
            "accept": fsm.can(app.status, "accept_offer") and app.decision in ("APPROVED", "COUNTER_OFFER"),
            "sign": fsm.can(app.status, "sign"),
            "edit": app.status == "DRAFT",
            "upload_documents": app.status != "DISBURSED",
        },
        **({"validation": validation} if validation is not None else {}),
    }


def application_detail(app: Application) -> dict:
    out = application_out(app)
    out["documents"] = [document_out(d, app) for d in app.documents]
    out["timeline"] = timeline(app)
    return out


def bank_row(app: Application) -> dict:
    s = app.scorings[-1] if app.scorings else None
    return {
        "id": app.id,
        "number": app.number,
        "company_name": app.company.name if app.company else None,
        "inn": app.company.inn if app.company else None,
        "requested_amount": app.requested_amount,
        "display": display_status(app),
        "status": app.status,
        "risk_score": s.risk_score if s else None,
        "risk_level": s.risk_level if s else None,
        "created_at": iso(app.created_at),
    }


def bank_detail(app: Application) -> dict:
    out = application_detail(app)
    s = app.scorings[-1] if app.scorings else None
    out["scoring"] = (
        None
        if not s
        else {
            "risk_score": s.risk_score,
            "score_100": round(s.risk_score / 10),
            "risk_level": s.risk_level,
            "risk_level_label": _RISK_RU[s.risk_level],
            "factors": s.factors_json,
            "summary": s.summary,
            "created_at": iso(s.created_at),
        }
    )
    out["enrichment"] = (
        {e.source: {"payload": e.payload_json, "fetched_at": iso(e.fetched_at)} for e in app.enrichment[-2:]}
        if app.enrichment
        else {}
    )
    out["history"] = [
        {
            "from": h.from_status,
            "to": h.to_status,
            "actor": h.actor,
            "comment": h.comment,
            "timestamp": iso(h.timestamp),
        }
        for h in app.history
    ]
    out["available_actions"] = {
        t: fsm.can(app.status, t) for t in ("manual_decide", "override_decision", "request_documents", "rerun")
    }
    out["product_limits"] = (
        None
        if not app.product
        else {
            "min_sum": app.product.min_sum,
            "max_sum": app.product.max_sum,
            "min_term": app.product.min_term,
            "max_term": app.product.max_term,
            "base_rate": app.product.base_rate,
        }
    )
    return out
