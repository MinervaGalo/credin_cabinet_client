import io

PRODUCT = {"Бизнес-старт": 1, "Оборотный": 2, "На оборудование": 3}


def new_app(client, h, inn, amount=3_000_000, term=12, product=2, name="Тест"):
    r = client.post(
        "/api/applications",
        headers=h,
        json=dict(
            product_id=product,
            requested_amount=amount,
            term_months=term,
            purpose="Закупка товара",
            inn=inn,
            company_name=name,
        ),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def submit(client, h, app_id):
    r = client.post(f"/api/applications/{app_id}/submit", headers=h)
    assert r.status_code == 200, r.text
    return client.get(f"/api/applications/{app_id}", headers=h).json()  # фон отработал к моменту ответа TestClient


def test_seed_matches_frontend_demo(client, anna):
    apps = {a["number"]: a for a in client.get("/api/applications", headers=anna).json()}
    assert apps["КР-2026-0148"]["display"]["label"] == "На проверке"
    assert apps["КР-2026-0149"]["display"]["label"] == "Нужны документы"
    assert apps["КР-2026-0150"]["display"]["label"] == "Одобрена"
    assert len(client.get("/api/products").json()) == 3


def test_auth_and_roles(client, anna, analyst):
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/bank/applications", headers=anna).status_code == 403  # клиент не видит кабинет банка
    assert client.get("/api/applications", headers=analyst).status_code == 403
    bad = client.post("/api/auth/login", json={"email": "anna@example.test", "password": "x"})
    assert bad.status_code == 401 and "Неверный email" in bad.json()["error"]["message"]


def test_wizard_draft_and_live_validation(client, anna):
    r = client.post("/api/applications", headers=anna, json={"product_id": 2})  # пустой черновик
    app_id = r.json()["id"]
    assert r.json()["status"] == "DRAFT" and r.json()["validation"]["completeness"] < 50

    r = client.patch(f"/api/applications/{app_id}", headers=anna, json={"requested_amount": 20_000_000})
    errs = r.json()["validation"]["errors"]
    assert errs[0]["field"] == "requested_amount" and "не более 15 000 000 ₽" in errs[0]["message"]
    assert (
        "Оборотный" not in errs[0]["hint"] and "Уменьшите сумму до 15 000 000 ₽" in errs[0]["hint"]
    )  # подходящего продукта на 20 млн нет
    v = client.post("/api/applications/validate", headers=anna, json={"product_id": 1, "requested_amount": 8_000_000})
    assert "«Оборотный»" in v.json()["errors"][0]["hint"]  # а на 8 млн подходит другой
    assert r.json()["requested_amount"] == 20_000_000  # черновик сохранён, несмотря на ошибку

    r = client.patch(f"/api/applications/{app_id}", headers=anna, json={"term_months": 36})
    assert any("от 3 до 24 месяцев" in e["message"] for e in r.json()["validation"]["errors"])

    r = client.post(f"/api/applications/{app_id}/submit", headers=anna)  # отправка блокируется
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_error" and {f["field"] for f in body["fields"]} >= {
        "requested_amount",
        "term_months",
        "inn",
        "purpose",
    }

    r = client.post("/api/applications/validate", headers=anna, json={"inn": "12ab"})  # stateless-проверка
    assert "10 цифр" in r.json()["errors"][0]["message"]


def test_type_errors_are_human_readable(client, anna):
    r = client.post("/api/applications", headers=anna, json={"requested_amount": "много"})
    assert r.status_code == 422
    assert "нужно указать число" in r.json()["error"]["fields"][0]["message"]


def test_invalid_transition_is_409_with_hint(client, anna):
    r = client.post("/api/applications/1/submit", headers=anna)  # уже отправлена
    assert r.status_code == 409
    r = client.post("/api/applications/1/sign", headers=anna)
    assert r.status_code == 409 and r.json()["error"]["hint"]


def test_pipeline_low_risk_auto_approved(client, anna):
    a = submit(client, anna, new_app(client, anna, "7801122334", amount=2_000_000, name="ООО «Вектор»"))
    assert a["status"] == "DECISION_MADE" and a["decision"] == "APPROVED" and a["approved_amount"] == 2_000_000
    assert a["actions"]["accept"] is True


def test_pipeline_high_risk_rejected(client, anna):
    a = submit(client, anna, new_app(client, anna, "7700000001"))
    assert a["decision"] == "REJECTED" and a["display"]["css"] == "rejected"


def test_pipeline_stop_list_industry_rejected(client, anna, analyst):
    app_id = new_app(client, anna, "7700000002")
    submit(client, anna, app_id)
    d = client.get(f"/api/bank/applications/{app_id}", headers=analyst).json()
    assert d["decision"] == "REJECTED" and d["scoring"]["risk_level"] == "HIGH"
    assert any(f["rule"] == "stop_industry" for f in d["scoring"]["factors"])
    assert "стоп-лист" in d["scoring"]["summary"].lower() or "ограничений" in d["decision_reason"]


def test_pipeline_borderline_goes_to_manual_review(client, anna, analyst):
    app_id = new_app(client, anna, "7812345678", amount=1_000_000, name="ООО «Север»")
    a = submit(client, anna, app_id)
    assert a["status"] == "MANUAL_REVIEW"
    d = client.get(f"/api/bank/applications/{app_id}", headers=analyst).json()
    assert d["scoring"]["risk_level"] == "MEDIUM" and d["enrichment"]["FNS"] and d["enrichment"]["BKI"]
    assert d["scoring"]["factors"][0]["rule"] == "base"


def test_analyst_manual_flow_and_audit(client, anna, analyst):
    app_id = new_app(client, anna, "7812345678", amount=3_000_000, name="ООО «Север»")
    submit(client, anna, app_id)

    r = client.post(
        f"/api/bank/applications/{app_id}/request-documents",
        headers=analyst,
        json={"comment": "Пришлите выписку за 6 месяцев"},
    )
    assert r.json()["status"] == "DOCUMENTS_REQUESTED"
    mine = client.get(f"/api/applications/{app_id}", headers=anna).json()
    assert mine["documents_request_comment"] == "Пришлите выписку за 6 месяцев"

    up = client.post(
        f"/api/applications/{app_id}/documents",
        headers=anna,
        data={"type": "STATEMENT"},
        files={
            "file": (
                "vypiska.txt",
                io.BytesIO("Выручка за 2025 год: 28 800 000 руб.\nЧистая прибыль: 2 600 000".encode()),
                "text/plain",
            )
        },
    )
    assert up.status_code == 201 and up.json()["parsed_data"]["revenue"] == 28_800_000  # ИИ-разбор положил цифры
    assert client.get(f"/api/applications/{app_id}", headers=anna).json()["status"] == "MANUAL_REVIEW"

    assert (
        client.post(f"/api/bank/applications/{app_id}/reject", headers=analyst, json={"reason": ""}).status_code == 422
    )
    assert (
        client.post(
            f"/api/bank/applications/{app_id}/counter-offer", headers=analyst, json={"amount": 99_000_000}
        ).status_code
        == 422
    )
    r = client.post(
        f"/api/bank/applications/{app_id}/counter-offer",
        headers=analyst,
        json={"amount": 2_000_000, "rate": 15.0, "comment": "Нужен залог"},
    )
    assert r.json()["decision"] == "COUNTER_OFFER" and r.json()["approved_amount"] == 2_000_000

    r = client.post(
        f"/api/bank/applications/{app_id}/approve", headers=analyst, json={}
    )  # пересмотр до принятия клиентом
    assert r.json()["decision"] == "APPROVED"

    client.post(f"/api/applications/{app_id}/accept", headers=anna)
    assert (
        client.post(f"/api/bank/applications/{app_id}/approve", headers=analyst, json={}).status_code == 409
    )  # после принятия - нельзя
    client.post(f"/api/applications/{app_id}/sign", headers=anna)
    assert client.get(f"/api/applications/{app_id}", headers=anna).json()["status"] == "DISBURSED"

    audit = client.get(f"/api/bank/applications/{app_id}/history", headers=analyst).json()
    path = [h["to"] for h in audit]
    assert path[:5] == ["DRAFT", "SUBMITTED", "DATA_ENRICHMENT", "SCORING", "MANUAL_REVIEW"] and path[-1] == "DISBURSED"
    assert any(h["actor"] == "analyst:analyst@bank.test" and h["comment"] for h in audit)


def test_rerun_scoring(client, anna, analyst):
    app_id = new_app(client, anna, "7812345678", amount=1_000_000, name="ООО «Север»")
    submit(client, anna, app_id)
    r = client.post(f"/api/bank/applications/{app_id}/rerun-scoring", headers=analyst)
    assert r.status_code == 200
    d = client.get(f"/api/bank/applications/{app_id}", headers=analyst).json()
    assert d["status"] == "MANUAL_REVIEW" and len(d["history"]) > 6


def test_mock_outage_falls_back_to_manual_review(client, anna):
    app_id = new_app(client, anna, "0000000000")  # мок отвечает 503
    a = submit(client, anna, app_id)
    assert a["status"] == "MANUAL_REVIEW"


def test_bank_dashboard_and_filters(client, analyst):
    s = client.get("/api/bank/stats", headers=analyst).json()
    assert s["total"] >= 3 and s["approved"] >= 1 and s["review"] >= 1
    rows = client.get("/api/bank/applications", params={"status": "Нужны документы"}, headers=analyst).json()
    assert rows and all(r["display"]["label"] == "Нужны документы" for r in rows)
    assert (
        client.get("/api/bank/applications", params={"q": "7801122334"}, headers=analyst).json()[0]["company_name"]
        == "ООО «Вектор»"
    )


def test_documents_and_notifications(client, anna):
    docs = client.get("/api/documents", headers=anna).json()
    assert {d["filename"] for d in docs} >= {
        "Бухгалтерская отчётность.pdf",
        "Выписка по счёту.pdf",
        "Счёт на оборудование.pdf",
    }
    bad = client.post("/api/applications/1/documents", headers=anna, files={"file": ("virus.exe", io.BytesIO(b"x"))})
    assert bad.status_code == 422 and "не поддерживается" in bad.json()["error"]["message"]
    assert client.get("/api/notifications", headers=anna).json()


def test_ai_assistant(client, anna):
    r = client.post(
        "/api/ai/assistant", headers=anna, json={"message": "Нужно 5 миллионов на закупку оборудования на полгода"}
    ).json()
    assert r["product"] == "На оборудование" and r["prefill"]["requested_amount"] == 5_000_000
    assert r["prefill"]["term_months"] == 12 and r["notes"]  # срок подогнан под продукт и это объяснено
    r = client.post(
        "/api/ai/assistant", headers=anna, json={"message": "хочу 300 тысяч на зарплаты на 3 месяца"}
    ).json()
    assert (
        r["product"] == "Оборотный" and r["prefill"]["requested_amount"] == 300_000 and r["prefill"]["term_months"] == 3
    )


def test_company_lookup(client, anna):
    assert client.get("/api/companies/lookup/7801122334", headers=anna).json()["name"] == "ООО «Вектор»"
    assert client.get("/api/companies/lookup/0000000000", headers=anna).status_code == 404


def test_registration_and_login(client):
    body = {"email": "New.Owner@Example.com", "password": "strong-pass-1", "full_name": "Ирина Новикова"}
    registered = client.post("/api/auth/register", json=body)
    assert registered.status_code == 201 and registered.json()["role"] == "client"

    headers = {"Authorization": f"Bearer {registered.json()['token']}"}
    assert client.get("/api/me", headers=headers).json()["email"] == "new.owner@example.com"
    login = client.post("/api/auth/login", json={"email": "new.owner@example.com", "password": "strong-pass-1"})
    assert login.status_code == 200

    again = client.post("/api/auth/register", json=body)
    assert again.status_code == 409 and again.json()["error"]["code"] == "email_taken"


def test_registration_validation_messages(client):
    response = client.post("/api/auth/register", json={"email": "no-at-sign", "password": "short", "full_name": "И"})
    assert response.status_code == 422
    messages = " ".join(f["message"] for f in response.json()["error"]["fields"])
    assert "name@example.com" in messages and "слишком коротко" in messages


def test_forged_and_expired_tokens_are_rejected(client):
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app import config

    expired = jwt.encode(
        {"sub": "1", "role": "client", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        config.SECRET_KEY,
        "HS256",
    )
    forged = jwt.encode({"sub": "1", "role": "analyst", "exp": 9999999999}, "wrong-key", "HS256")
    for token in (expired, forged, "not-a-token"):
        response = client.get("/api/bank/stats", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def render_text_image(text: str):
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    font_path = next((p for p in FONT_PATHS if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default(48)
    image = Image.new("RGB", (1700, 140), "white")
    ImageDraw.Draw(image).text((20, 30), text, fill="black", font=font)
    return image


def test_ocr_reads_digits_from_image_and_scanned_pdf(tmp_path):
    import pytest

    from app import ocr

    if not ocr.is_available():
        pytest.skip("Tesseract не установлен")
    image = render_text_image("Revenue 28800000")
    assert "28800000" in ocr.image_to_text(image).replace(" ", "")

    scan = tmp_path / "scan.pdf"
    image.save(scan)  # PDF из картинки: текстового слоя нет
    assert "28800000" in ocr.file_to_text(scan).replace(" ", "")


def test_scanned_statement_is_parsed_after_upload(client, anna):
    import pytest

    from app import ocr

    if "rus" not in ocr._languages():
        pytest.skip("Не установлен русский язык Tesseract")
    app_id = new_app(client, anna, "7812345678", name="ООО «Север»")
    buffer = io.BytesIO()
    render_text_image("Выручка за 2025 год: 28 800 000 руб.").save(buffer, format="PNG")
    buffer.seek(0)
    uploaded = client.post(
        f"/api/applications/{app_id}/documents",
        headers=anna,
        data={"type": "STATEMENT"},
        files={"file": ("scan.png", buffer, "image/png")},
    )
    assert uploaded.status_code == 201 and uploaded.json()["parsed_data"]["revenue"] == 28_800_000


def test_migrations_match_models(tmp_path):
    """Миграции создают ровно ту схему, что описана в моделях, и откатываются без ошибок."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    from app import config
    from app.db import Base

    url = f"sqlite:///{tmp_path}/migrations.db"
    old_url, config.DATABASE_URL = config.DATABASE_URL, url
    try:
        alembic_config = Config(str(__import__("pathlib").Path(config.__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(alembic_config, "head")
        engine = create_engine(url)
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        engine.dispose()
        command.downgrade(alembic_config, "base")
    finally:
        config.DATABASE_URL = old_url
