"""Decision Engine: уровень риска и продукт превращаются в решение.

LOW - одобрение; MEDIUM - встречное предложение или ручная проверка (по баллу); HIGH - отказ.
"""

from . import config


def decide(risk_level: str, risk_score: int, amount: int, term: int, product, hard_stop: bool = False) -> dict:
    rate = product.base_rate

    if risk_level == "HIGH":
        reason = (
            "Отрасль деятельности входит в список ограничений банка"
            if hard_stop
            else "Уровень риска по заявке выше допустимого для автоматического одобрения"
        )
        return {"decision": "REJECTED", "next": "decide", "amount": None, "rate": None, "reason": reason}

    if risk_level == "LOW":
        return {
            "decision": "APPROVED",
            "next": "decide",
            "amount": amount,
            "rate": rate,
            "reason": "Низкий риск, заявка одобрена автоматически",
        }

    if risk_score >= config.AUTO_COUNTER_MIN_SCORE:
        reduced_amount = max(product.min_sum, int(round(amount * config.COUNTER_AMOUNT_FACTOR, -3)))
        return {
            "decision": "COUNTER_OFFER",
            "next": "decide",
            "amount": reduced_amount,
            "rate": round(rate + config.COUNTER_RATE_ADD, 2),
            "reason": "Средний риск: банк готов одобрить меньшую сумму на скорректированных условиях",
        }

    return {
        "decision": None,
        "next": "send_to_review",
        "amount": None,
        "rate": None,
        "reason": "Пограничный риск: заявка передана кредитному аналитику",
    }
