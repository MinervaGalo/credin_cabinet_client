"""Mock-service: эмулятор внешних систем (ФНС/ЕГРЮЛ и БКИ).

Реальные API недоступны, поэтому core обращается сюда. Для тестовых ИНН возвращаются заранее
подобранные данные, чтобы исход заявки был предсказуем; для остальных данные строятся
по хэшу ИНН, и один и тот же ИНН всегда даёт один и тот же ответ.
"""

import hashlib
import os
import time
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException

LATENCY_MS = int(os.getenv("MOCK_LATENCY_MS", "0"))  # искусственная задержка ответа
FAIL_INN = "0000000000"  # по этому ИНН мок отвечает 503
TODAY = date.today()

app = FastAPI(
    title="Mock Service (ФНС / БКИ)",
    description="Синтетические данные внешних систем для демонстрации кредитного конвейера.",
    version="1.0.0",
)

# Данные подобраны так, чтобы скоринг давал ожидаемый исход (см. таблицу в README).
SCENARIOS = {
    "7812345678": dict(
        label="Пограничный клиент (ручная проверка)",
        fns=dict(
            name="ООО «Север»",
            ogrn="1127847000011",
            years=3,
            okved="46.90",
            revenue_monthly=2_400_000,
            net_profit=2_600_000,
            taxes=1_900_000,
            arrears=0,
            employees=18,
        ),
        bki=dict(
            active_loans=3, total_debt=1_800_000, overdue_count=0, max_overdue_days=0, credit_rating=560, inquiries=3
        ),
    ),
    "781234567890": dict(
        label="Молодой бизнес (мало данных)",
        fns=dict(
            name="ИП Иванов Иван Иванович",
            ogrn="319784700012345",
            years=1,
            okved="47.19",
            revenue_monthly=1_200_000,
            net_profit=1_100_000,
            taxes=310_000,
            arrears=0,
            employees=3,
        ),
        bki=dict(
            active_loans=1, total_debt=300_000, overdue_count=0, max_overdue_days=0, credit_rating=560, inquiries=2
        ),
    ),
    "7801122334": dict(
        label="Надёжный клиент (автоодобрение)",
        fns=dict(
            name="ООО «Вектор»",
            ogrn="1089847000099",
            years=9,
            okved="25.62",
            revenue_monthly=14_500_000,
            net_profit=38_000_000,
            taxes=21_000_000,
            arrears=0,
            employees=96,
        ),
        bki=dict(
            active_loans=1, total_debt=2_000_000, overdue_count=0, max_overdue_days=0, credit_rating=830, inquiries=1
        ),
    ),
    "7700000001": dict(
        label="Просрочки и долги (отказ)",
        fns=dict(
            name="ООО «Кедр-Трейд»",
            ogrn="1157700000001",
            years=4,
            okved="46.41",
            revenue_monthly=1_900_000,
            net_profit=-1_200_000,
            taxes=400_000,
            arrears=650_000,
            employees=11,
        ),
        bki=dict(
            active_loans=6, total_debt=9_500_000, overdue_count=4, max_overdue_days=94, credit_rating=310, inquiries=9
        ),
    ),
    "7700000002": dict(
        label="Отрасль из стоп-листа (отказ)",
        fns=dict(
            name="ООО «Фортуна Гейминг»",
            ogrn="1167700000002",
            years=6,
            okved="92.00",
            revenue_monthly=11_000_000,
            net_profit=30_000_000,
            taxes=15_000_000,
            arrears=0,
            employees=45,
        ),
        bki=dict(
            active_loans=1, total_debt=1_000_000, overdue_count=0, max_overdue_days=0, credit_rating=700, inquiries=2
        ),
    ),
}

OKVED_POOL = ["46.90", "47.11", "49.41", "56.10", "62.01", "41.20", "25.62", "10.71", "68.20", "43.21"]


def _hash_seed(inn: str) -> int:
    return int(hashlib.sha256(inn.encode()).hexdigest()[:12], 16)


def _generated(inn: str) -> dict:
    """Детерминированные данные для ИНН, которого нет среди тестовых."""
    seed = _hash_seed(inn)
    rating = 350 + seed % 500  # 350..849
    overdue = 0 if rating > 520 else (seed // 7) % 3 + 1
    return dict(
        label="Сгенерировано по хэшу ИНН",
        fns=dict(
            name=f"Компания {inn}",
            ogrn=f"11{inn.zfill(11)[:11]}0",
            years=1 + (seed // 3) % 10,
            okved=OKVED_POOL[(seed // 11) % len(OKVED_POOL)],
            revenue_monthly=400_000 + (seed // 13) % 12_000_000,
            net_profit=(seed // 17) % 20_000_000 - 2_000_000,
            taxes=(seed // 19) % 8_000_000,
            arrears=0 if (seed // 23) % 5 else 150_000,
            employees=2 + (seed // 29) % 80,
        ),
        bki=dict(
            active_loans=(seed // 31) % 6,
            total_debt=((seed // 37) % 8) * 500_000,
            overdue_count=overdue,
            max_overdue_days=overdue * 20,
            credit_rating=rating,
            inquiries=(seed // 41) % 8,
        ),
    )


def _scenario(key: str) -> dict:
    return SCENARIOS.get(key) or _generated(key)


def _check(inn: str) -> None:
    if LATENCY_MS:
        time.sleep(LATENCY_MS / 1000)
    if inn == FAIL_INN:
        raise HTTPException(503, "Сервис временно недоступен (имитация сбоя)")
    if not inn.isdigit() or len(inn) not in (10, 11, 12):
        raise HTTPException(422, "ИНН / СНИЛС должен состоять из 10–12 цифр")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/mock/scenarios", summary="Список тестовых ИНН и ожидаемых исходов")
def scenarios():
    return [{"inn": inn, "company": item["fns"]["name"], "scenario": item["label"]} for inn, item in SCENARIOS.items()]


@app.get("/mock/fns/{inn}", summary="Синтетические данные ЕГРЮЛ/ФНС")
def fns(inn: str):
    _check(inn)
    data = _scenario(inn)["fns"]
    registered = TODAY - timedelta(days=int(data["years"] * 365.25) + 40)
    return {
        "inn": inn,
        "ogrn": data["ogrn"],
        "name": data["name"],
        "status": "ACTIVE",
        "registration_date": registered.isoformat(),
        "industry_code": data["okved"],
        "revenue_last_12m": data["revenue_monthly"] * 12,
        "revenue_monthly_avg": data["revenue_monthly"],
        "net_profit_last_year": data["net_profit"],
        "taxes_paid_last_year": data["taxes"],
        "tax_arrears": data["arrears"],
        "employees": data["employees"],
        "source": "mock-fns",
    }


@app.get("/mock/bki/{inn_or_snils}", summary="Синтетическая кредитная история")
def bki(inn_or_snils: str):
    _check(inn_or_snils)
    data = _scenario(inn_or_snils)["bki"]
    return {
        "subject": inn_or_snils,
        "active_loans": data["active_loans"],
        "total_debt": data["total_debt"],
        "has_overdue_last_12m": data["overdue_count"] > 0,
        "overdue_count_last_12m": data["overdue_count"],
        "max_overdue_days": data["max_overdue_days"],
        "credit_rating": data["credit_rating"],  # 0..1000, больше - лучше
        "inquiries_last_90d": data["inquiries"],
        "source": "mock-bki",
    }
