"""Проверка заявки по мере заполнения мастера.

Ошибки блокируют отправку, предупреждения только сообщают о возможной опечатке.
Тексты написаны для предпринимателя, а не для финансиста.
"""

import re

from . import config

REQUIRED = ["product_id", "requested_amount", "term_months", "purpose", "inn", "company_name"]
STEP_FIELDS = {1: ["product_id", "requested_amount", "term_months", "purpose"], 2: ["company_name", "inn"]}


def _checksum(inn: str, weights: list[int]) -> int:
    return sum(int(digit) * weight for digit, weight in zip(inn, weights)) % 11 % 10


def inn_checksum_ok(inn: str) -> bool:
    if len(inn) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return int(inn[9]) == _checksum(inn, weights)
    if len(inn) == 12:
        first = _checksum(inn, [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        second = _checksum(inn, [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        return int(inn[10]) == first and int(inn[11]) == second
    return False


def _rub(x: int) -> str:
    return f"{x:,}".replace(",", " ") + " ₽"


def _alternative(products, amount, term, current):
    """Другой продукт, под который подходят и сумма, и срок (если они указаны)."""
    for p in products or []:
        if current and p.id == current.id:
            continue
        if (amount is None or p.min_sum <= amount <= p.max_sum) and (term is None or p.min_term <= term <= p.max_term):
            return p
    return None


def validate_application(data: dict, product=None, strict: bool = False, products=None) -> dict:
    """Проверяет поля заявки. При strict=True пустые обязательные поля считаются ошибками (отправка заявки)."""
    errors, warnings = [], []

    def err(field, msg, hint=None):
        errors.append({"field": field, "message": msg, "hint": hint})

    def has(f):
        return data.get(f) not in (None, "")

    if strict:
        names = {
            "product_id": "кредитный продукт",
            "requested_amount": "сумму кредита",
            "term_months": "срок",
            "purpose": "цель финансирования",
            "inn": "ИНН компании",
            "company_name": "название компании",
        }
        for f in REQUIRED:
            if not has(f):
                err(f, f"Укажите {names[f]}")

    amount, term = data.get("requested_amount"), data.get("term_months")
    pname = f"«{product.name}»" if product else "выбранного продукта"
    if has("requested_amount"):
        if amount < config.MIN_AMOUNT:
            err(
                "requested_amount",
                f"Минимальная сумма кредита - {_rub(config.MIN_AMOUNT)}",
                "Введите сумму цифрами, например 3000000",
            )
        elif product and amount < product.min_sum:
            err("requested_amount", f"Для продукта {pname} сумма от {_rub(product.min_sum)}")
        elif product and amount > product.max_sum:
            alt = _alternative(products, amount, term if has("term_months") else None, product)
            err(
                "requested_amount",
                f"Для продукта {pname} можно запросить не более {_rub(product.max_sum)}",
                (
                    f"Для такой суммы подойдёт «{alt.name}» (до {_rub(alt.max_sum)}) или уменьшите сумму"
                    if alt
                    else f"Уменьшите сумму до {_rub(product.max_sum)} или меньше"
                ),
            )
    if has("term_months"):
        if term <= 0:
            err("term_months", "Срок должен быть больше нуля")
        elif product and not (product.min_term <= term <= product.max_term):
            alt = _alternative(products, amount if has("requested_amount") else None, term, product)
            err(
                "term_months",
                f"Для продукта {pname} срок от {product.min_term} до {product.max_term} месяцев",
                (
                    f"Такой срок есть у продукта «{alt.name}» ({alt.min_term}–{alt.max_term} мес.) - или выберите срок из диапазона"
                    if alt
                    else "Выберите срок из этого диапазона"
                ),
            )
    if has("inn"):
        inn = str(data["inn"])
        if not re.fullmatch(r"\d{10}(\d{2})?", inn):
            err("inn", "ИНН состоит из 10 цифр (организация) или 12 цифр (ИП)", "Проверьте, что нет пробелов и букв")
        elif not inn_checksum_ok(inn):
            msg = "ИНН не проходит проверку контрольной суммы - возможно, опечатка"
            if config.VALIDATE_INN_CHECKSUM:
                err("inn", msg, "Сверьте номер с документами компании")
            else:
                warnings.append({"field": "inn", "message": msg})
    if has("company_name") and len(str(data["company_name"]).strip()) < 2:
        err("company_name", "Название компании слишком короткое")
    if has("purpose") and len(str(data["purpose"]).strip()) < 3:
        err("purpose", "Опишите цель финансирования хотя бы в двух словах")

    filled = sum(1 for f in REQUIRED if has(f))
    steps = {}
    for step, fields in STEP_FIELDS.items():
        bad = {e["field"] for e in errors}
        steps[step] = "done" if all(has(f) for f in fields) and not (bad & set(fields)) else "in_progress"
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "completeness": round(100 * filled / len(REQUIRED)),
        "steps": steps,
    }
