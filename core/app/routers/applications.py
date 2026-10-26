"""API клиента: мастер заявки, черновики, документы, уведомления."""

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai, config, ocr
from .. import statemachine as fsm
from ..crud import (
    all_products,
    app_to_form,
    create_application,
    get_product,
    upsert_company,
)
from ..db import get_db
from ..deps import actor, client_user, current_user
from ..errors import AppError
from ..models import Application, ApplicationStateHistory, Document, User
from ..schemas import ApplicationIn
from ..serializers import application_detail, application_out, document_out
from ..tasks import enqueue
from ..validation import validate_application

router = APIRouter(prefix="/api", tags=["client"])

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"}
MAX_FILE_MB = 10
DOCUMENT_TYPES = {"BALANCE", "STATEMENT", "INVOICE", "OTHER"}
EDITABLE_FIELDS = ("product_id", "requested_amount", "term_months", "purpose")
INTERNAL_STATUSES = ("DATA_ENRICHMENT", "SCORING")


def my_app(db: Session, app_id: int, user: User) -> Application:
    app = db.get(Application, app_id)
    if not app or app.user_id != user.id:
        raise AppError(
            "Заявка не найдена", 404, "not_found", "Возможно, она принадлежит другой компании или была удалена"
        )
    return app


@router.get("/applications", summary="Мои заявки (с поиском по номеру или названию компании)")
def list_applications(q: str | None = None, user: User = Depends(client_user), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.user_id == user.id).order_by(Application.id.desc())).all()
    if q:
        query = q.lower()
        apps = [a for a in apps if query in (a.number or "").lower() or (a.company and query in a.company.name.lower())]
    return [application_out(a) for a in apps]


@router.post("/applications/validate", summary="Проверка полей по мере ввода, без сохранения")
def validate_only(body: ApplicationIn, user: User = Depends(client_user), db: Session = Depends(get_db)):
    data = body.model_dump()
    return validate_application(data, get_product(db, data["product_id"]), products=all_products(db))


@router.post("/applications", status_code=201, summary="Создать черновик (можно с частью полей)")
def create(body: ApplicationIn, user: User = Depends(client_user), db: Session = Depends(get_db)):
    data = body.model_dump()
    product = get_product(db, data["product_id"])
    validation = validate_application(data, product, products=all_products(db))
    if any(error["field"] == "inn" for error in validation["errors"]):
        data["inn"] = None  # некорректный ИНН не должен попасть в справочник компаний
    app = create_application(db, user, data, actor(user))
    db.commit()
    return application_out(app, validation=validation)


@router.get("/applications/{app_id}", summary="Заявка целиком: параметры, документы, история")
def detail(app_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    return application_detail(my_app(db, app_id, user))


@router.patch("/applications/{app_id}", summary="Сохранить шаг мастера (частичное обновление черновика)")
def patch(app_id: int, body: ApplicationIn, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = my_app(db, app_id, user)
    if app.status != "DRAFT":
        raise AppError(
            "Заявку уже отправили в банк, изменить параметры нельзя",
            409,
            "not_editable",
            "Если нужно что-то поправить, свяжитесь со службой поддержки или создайте новую заявку",
        )

    changes = body.model_dump(exclude_unset=True)
    form = {**app_to_form(app), **changes}
    validation = validate_application(form, get_product(db, form["product_id"]), products=all_products(db))
    invalid_fields = {error["field"] for error in validation["errors"]}

    for field in EDITABLE_FIELDS:
        if field in changes:
            setattr(app, field, changes[field])
    if ("inn" in changes or "company_name" in changes) and "inn" not in invalid_fields:
        company = upsert_company(db, form["inn"], form["company_name"])
        app.company_id = company.id if company else None
    db.commit()
    db.refresh(app)
    return application_out(app, validation=validation)


@router.post("/applications/{app_id}/submit", summary="Отправить заявку в банк (строгая проверка и запуск конвейера)")
def submit(app_id: int, background: BackgroundTasks, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = my_app(db, app_id, user)
    if app.status != "DRAFT":
        raise AppError("Эта заявка уже отправлена в банк", 409, "already_submitted")

    validation = validate_application(app_to_form(app), app.product, strict=True, products=all_products(db))
    attached_types = {doc.type for doc in app.documents}
    for doc_type in config.MIN_REQUIRED_DOC_TYPES:
        if doc_type not in attached_types:
            validation["errors"].append({"field": "documents", "message": f"Приложите документ: {doc_type}"})
    if validation["errors"]:
        raise AppError(
            "Заявку пока нельзя отправить - нужно поправить несколько полей",
            422,
            "validation_error",
            fields=validation["errors"],
        )

    fsm.fire(db, app, "submit", actor(user), "Клиент отправил заявку")
    db.commit()
    enqueue(app.id, background)
    return application_out(app)


@router.post("/applications/{app_id}/accept", summary="Принять предложение банка (одобренную сумму и ставку)")
def accept(app_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = my_app(db, app_id, user)
    if app.decision not in ("APPROVED", "COUNTER_OFFER"):
        raise AppError("Принять можно только одобренную заявку", 409, "not_approved")
    fsm.fire(db, app, "accept_offer", actor(user), "Клиент принял условия банка")
    db.commit()
    return application_out(app)


@router.post("/applications/{app_id}/sign", summary="Подписать договор (в демо подпись мгновенная, деньги «выдаются»)")
def sign(app_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = my_app(db, app_id, user)
    fsm.fire(db, app, "sign", actor(user), "Договор подписан, средства выданы")
    db.commit()
    return application_out(app)


@router.get("/applications/{app_id}/history", summary="Хронология заявки")
def history(app_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = my_app(db, app_id, user)
    visible = [entry for entry in app.history if entry.to_status not in INTERNAL_STATUSES]
    return [{"status": e.to_status, "comment": e.comment, "timestamp": e.timestamp.isoformat()} for e in visible]


def _extract_text(path: str) -> str:
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".txt":
        return file.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        text = "\n".join((page.extract_text() or "") for page in PdfReader(str(file)).pages)
        if text.strip():
            return text
    if suffix == ".pdf" or suffix in ocr.IMAGE_SUFFIXES:
        return ocr.file_to_text(file)  # скан или фото: текстового слоя нет
    return ""


def _parse_document(doc: Document, app: Application) -> dict:
    text = _extract_text(doc.file_path) if doc.file_path else ""
    data = ai.parse_financials(text) if text.strip() else {}
    doc.parsed_data_json = data or None
    if data and app.company:
        parsed = {f"doc_{key}": value for key, value in data.items()}
        app.company.financial_metrics = {**(app.company.financial_metrics or {}), **parsed}
    return data


def _save_upload(app: Application, file: UploadFile) -> Path:
    content = file.file.read()
    if len(content) > MAX_FILE_MB * 1024 * 1024:
        raise AppError(
            f"Файл больше {MAX_FILE_MB} МБ", 413, "file_too_big", "Сожмите файл или разделите на несколько частей"
        )
    folder = Path(config.UPLOAD_DIR) / str(app.id)
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]+", "_", file.filename or "file")
    path = folder / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    path.write_bytes(content)
    return path


@router.post(
    "/applications/{app_id}/documents",
    status_code=201,
    summary="Загрузить документ (PDF, TXT, PNG, JPG, DOCX, XLSX до 10 МБ)",
)
def upload(
    app_id: int,
    file: UploadFile = File(...),
    type: str = Form("OTHER"),
    user: User = Depends(client_user),
    db: Session = Depends(get_db),
):
    app = my_app(db, app_id, user)
    if Path(file.filename or "").suffix.lower() not in ALLOWED_EXTENSIONS:
        raise AppError(
            "Этот тип файла не поддерживается",
            422,
            "bad_file",
            "Загрузите PDF, фото (PNG/JPG), Word или Excel",
            [{"field": "file", "message": "Допустимы: PDF, TXT, PNG, JPG, DOCX, XLSX"}],
        )
    doc_type = type if type in DOCUMENT_TYPES else "OTHER"

    path = _save_upload(app, file)
    doc = Document(application_id=app.id, type=doc_type, filename=file.filename, file_path=str(path))
    db.add(doc)
    db.flush()

    if doc_type in ("BALANCE", "STATEMENT"):
        try:
            _parse_document(doc, app)
        except Exception:
            pass  # разбор отчётности - дополнение: его сбой не должен срывать загрузку файла

    if app.status == "DOCUMENTS_REQUESTED":
        fsm.fire(db, app, "documents_provided", actor(user), f"Клиент загрузил документ: {file.filename}")
    db.commit()
    return document_out(doc, app)


@router.get("/documents", summary="Все документы по моим заявкам")
def all_documents(user: User = Depends(client_user), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.user_id == user.id).order_by(Application.id)).all()
    return [document_out(doc, app) for app in apps for doc in app.documents]


@router.get("/applications/{app_id}/documents", summary="Документы одной заявки")
def app_documents(app_id: int, user: User = Depends(client_user), db: Session = Depends(get_db)):
    app = my_app(db, app_id, user)
    return [document_out(doc, app) for doc in app.documents]


def _find_document(db: Session, doc_id: int, user: User) -> tuple[Document, Application]:
    doc = db.get(Document, doc_id)
    app = db.get(Application, doc.application_id) if doc else None
    if not doc or (user.role == "client" and app.user_id != user.id):
        raise AppError("Документ не найден", 404, "not_found")
    return doc, app


@router.get("/documents/{doc_id}/download", summary="Скачать документ (клиент - свой, аналитик - любой)")
def download(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = _find_document(db, doc_id, user)
    if not doc.file_path or not Path(doc.file_path).exists():
        raise AppError("Это демонстрационный документ - файла на сервере нет", 404, "demo_file")
    return FileResponse(doc.file_path, filename=doc.filename)


@router.post(
    "/documents/{doc_id}/parse",
    summary="Разбор отчётности: выручка, прибыль и чистые активы попадают в данные компании",
)
def parse(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, app = _find_document(db, doc_id, user)
    if not doc.file_path:
        raise AppError("В демонстрационном документе нет файла, разбирать нечего", 422, "demo_file")
    try:
        data = _parse_document(doc, app)
    except ocr.OcrUnavailable:
        raise AppError(
            "Распознавание сканов сейчас недоступно",
            503,
            "ocr_unavailable",
            "Загрузите PDF с текстовым слоем или TXT либо обратитесь в поддержку",
        )
    db.commit()
    return {"document_id": doc.id, "parsed_data": data, "engine": "ollama" if config.OLLAMA_URL else "rules"}


DECISION_NOTIFICATIONS = {"REJECTED": "принято решение: отказ", "COUNTER_OFFER": "банк предложил другие условия"}


def _notification_text(entry: ApplicationStateHistory, app: Application) -> str | None:
    texts = {
        "SUBMITTED": "отправлена в банк",
        "MANUAL_REVIEW": "на проверке у аналитика",
        "AWAITING_SIGNING": "ожидает подписания",
        "DISBURSED": "договор подписан, средства выданы",
        "DOCUMENTS_REQUESTED": "банк запросил документы" + (f": {entry.comment}" if entry.comment else ""),
        "DECISION_MADE": DECISION_NOTIFICATIONS.get(app.decision, "заявка одобрена"),
    }
    return texts.get(entry.to_status)


@router.get("/notifications", summary="Последние события по моим заявкам")
def notifications(user: User = Depends(client_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(ApplicationStateHistory, Application)
        .join(Application, Application.id == ApplicationStateHistory.application_id)
        .where(Application.user_id == user.id)
        .order_by(ApplicationStateHistory.id.desc())
        .limit(60)
    ).all()
    events = []
    for entry, app in rows:
        text = _notification_text(entry, app)
        if text:
            events.append(
                {
                    "application_id": app.id,
                    "title": f"Заявка {app.number}: {text}",
                    "timestamp": entry.timestamp.isoformat(),
                }
            )
    return events[:20]
