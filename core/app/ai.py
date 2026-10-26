"""ИИ-функции: ассистент клиента, разбор отчётности, пояснение скоринга для аналитика.

Если задан OLLAMA_URL, ответы уточняет локальная LLM. Без неё всё работает на правилах
и регулярных выражениях, поэтому демо не зависит от того, поднята ли модель.
"""

import json
import re

import httpx

from . import config

NUMBER = r"(\d+(?:[.,]\d+)?)"


def llm(prompt: str, system: str = "", as_json: bool = False) -> str | None:
    """Возвращает ответ модели или None, если модель отключена или недоступна."""
    if not config.OLLAMA_URL:
        return None
    payload = {
        "model": config.OLLAMA_MODEL,
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }
    if as_json:
        payload["format"] = "json"
    try:
        response = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=config.OLLAMA_TIMEOUT)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception:
        return None


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def _parse_amount(text: str) -> int | None:
    text = text.lower()
    if "полтора миллиона" in text:
        return 1_500_000
    if match := re.search(NUMBER + r"\s*(млн|миллион\w*|м\b)", text):
        return int(_to_float(match.group(1)) * 1_000_000)
    if match := re.search(NUMBER + r"\s*(тыс\w*|к\b)", text):
        return int(_to_float(match.group(1)) * 1_000)
    if match := re.search(r"(\d[\d\s]{4,}\d)", text):
        return int(re.sub(r"\s", "", match.group(1)))
    return None


def _parse_term(text: str) -> int | None:
    text = text.lower()
    if "полгода" in text or "пол года" in text:
        return 6
    if match := re.search(NUMBER + r"\s*(год|лет|года)", text):
        return int(_to_float(match.group(1)) * 12)
    if match := re.search(r"(\d+)\s*мес", text):
        return int(match.group(1))
    if re.search(r"\bна год\b|\bгод\b", text):
        return 12
    return None


# Правила идут от частных к общим: срабатывает первое совпавшее.
PRODUCT_RULES = [
    (r"оборудован|станок|станк|техник|автомобил|транспорт", "На оборудование", "Покупка оборудования"),
    (r"оборот|закупк|товар|сырь|зарплат|пополн|текущ", "Оборотный", "Пополнение оборотных средств"),
    (r"запуск|откры|развит|нов\w+ направлен|старт|расшир", "Бизнес-старт", "Развитие бизнеса"),
]


def _match_product(message: str, products: list):
    for pattern, product_name, purpose in PRODUCT_RULES:
        if re.search(pattern, message.lower()):
            return next((p for p in products if p.name == product_name), None), purpose
    return None, None


def _ask_llm_for_missing(message: str, products: list) -> dict:
    prompt = (
        f"Клиент написал: «{message}». Верни JSON "
        f'{{"amount": число в рублях|null, "term_months": число|null, "product": одно из {[p.name for p in products]}|null}}'
    )
    answer = llm(prompt, "Ты помогаешь выбрать кредит для малого бизнеса.", as_json=True)
    try:
        hints = json.loads(answer) if answer else {}
    except ValueError:
        return {}
    return hints if isinstance(hints, dict) else {}


def _fit_to_product(product, amount: int | None, term: int | None) -> tuple[int | None, int | None, list[str]]:
    """Подгоняет сумму и срок под ограничения продукта и объясняет каждое изменение."""
    notes = []
    if amount and amount > product.max_sum:
        max_sum = f"{product.max_sum:,}".replace(",", " ")
        notes.append(f"Максимум по продукту «{product.name}» - {max_sum} ₽, сумма уменьшена.")
        amount = product.max_sum
    if term and not product.min_term <= term <= product.max_term:
        fixed = min(max(term, product.min_term), product.max_term)
        notes.append(
            f"Срок по продукту «{product.name}» - от {product.min_term} до {product.max_term} мес., подставлен срок {fixed} мес."
        )
        term = fixed
    return amount, term, notes


def assistant(message: str, products: list) -> dict:
    amount, term = _parse_amount(message), _parse_term(message)
    product, purpose = _match_product(message, products)

    hints = _ask_llm_for_missing(message, products)
    amount = amount or hints.get("amount")
    term = term or hints.get("term_months")
    product = product or next((p for p in products if p.name == hints.get("product")), None)

    notes: list[str] = []
    if product:
        amount, term, notes = _fit_to_product(product, amount, term)

    prefill = {
        "product_id": product.id if product else None,
        "requested_amount": amount,
        "term_months": term,
        "purpose": purpose,
    }
    if product:
        rate = str(product.base_rate).replace(".", ",")
        parts = [f"Рекомендую «{product.name}» ({rate}% годовых)"]
        if amount:
            parts.append(f"сумма {amount:,} ₽".replace(",", " "))
        if term:
            parts.append(f"срок {term} мес")
        reply = ", ".join(parts) + ". Я заполнил форму заявки, проверьте и отправьте. " + " ".join(notes)
    else:
        reply = "Расскажите, на что нужны деньги (оборудование, закупка товара, развитие) и какая сумма - я подберу продукт."
    return {
        "reply": reply.strip(),
        "product": product.name if product else None,
        "prefill": prefill,
        "notes": notes,
        "engine": "ollama" if config.OLLAMA_URL else "rules",
    }


# Поле отчётности -> регулярное выражение для его названия в тексте.
FINANCIAL_FIELDS = {
    "revenue": r"выручк\w*|доход\w* от продаж",
    "net_profit": r"чист\w+ прибыл\w*",
    "net_assets": r"чист\w+ актив\w*",
    "balance_total": r"баланс|итого активов",
}


def _to_number(text: str) -> int:
    integer_part = text.split(",")[0].split(".")[0]
    return int(re.sub(r"[^\d]", "", integer_part) or 0)


def _find_amount(text: str, title_pattern: str) -> int | None:
    """Ищет значение после названия показателя, учитывая «за 2025 год» и множители «тыс»/«млн»."""
    pattern = rf"(?:{title_pattern})(?:\s+за\s+\d{{4}}\s*(?:год\w*|г\.?))?[^\d\-\n]{{0,40}}(-?\d[\d\s]{{3,}}\d)(\s*(?:тыс|млн))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    value = _to_number(match.group(1))
    unit = (match.group(2) or "").strip().lower()
    if unit.startswith("млн"):
        value *= 1_000_000
    elif unit.startswith("тыс"):
        value *= 1_000
    return -value if match.group(1).lstrip().startswith("-") else value


def parse_financials(text: str) -> dict:
    found = {}
    answer = llm(
        "Извлеки из текста отчётности JSON с полями revenue, net_profit, net_assets (рубли, числа, null если нет):\n"
        + text[:6000],
        "Ты финансовый аналитик.",
        as_json=True,
    )
    if answer:
        try:
            found = {key: value for key, value in json.loads(answer).items() if isinstance(value, (int, float))}
        except ValueError:
            found = {}

    for field, title_pattern in FINANCIAL_FIELDS.items():
        if field not in found and (value := _find_amount(text, title_pattern)) is not None:
            found[field] = value
    return found


LEVEL_RU = {"LOW": "низкий", "MEDIUM": "средний", "HIGH": "высокий"}
DECISION_RU = {
    "APPROVED": "Рекомендация: одобрить",
    "COUNTER_OFFER": "Рекомендация: встречное предложение",
    "REJECTED": "Рекомендация: отказать",
    None: "Требуется решение аналитика",
}


def _lower_first(text: str) -> str:
    """Первая буква строчная; остальной текст (например, «БКИ») не трогаем."""
    return text[:1].lower() + text[1:]


def explain(score: int, level: str, factors: list, decision: str | None) -> str:
    strengths = [f["description"] for f in factors if f["points"] > 0 and f["rule"] != "base"][:2]
    risks = [f["description"] for f in factors if f["points"] < 0][:3]

    parts = [f"{DECISION_RU.get(decision, '')}. Скоринг {score}/1000, риск {LEVEL_RU[level]}."]
    if strengths:
        parts.append("Сильные стороны: " + "; ".join(_lower_first(x) for x in strengths) + ".")
    if risks:
        parts.append("Факторы риска: " + "; ".join(_lower_first(x) for x in risks) + ".")
    if any(f["rule"] in ("many_loans", "load", "bki_overdue") for f in factors):
        parts.append("Рекомендуется запросить залог или поручительство.")
    elif level == "MEDIUM":
        parts.append("Рекомендуется запросить дополнительные документы (выписку по счёту, актуальную отчётность).")

    text = " ".join(parts)
    polished = llm(
        "Перепиши кратко и по-деловому для кредитного андеррайтера, не меняя фактов и цифр:\n" + text,
        "Ты помощник андеррайтера.",
    )
    return polished.strip() if polished else text
