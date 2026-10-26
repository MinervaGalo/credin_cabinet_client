"""Scoring Engine: балльная оценка риска. Решения здесь не принимаются."""

from datetime import date

from . import config


def _points_for(value, steps):
    for threshold, points, description in steps:
        if value >= threshold:
            return points, description
    return 0, ""


def level_for(score: int) -> str:
    if score >= config.LEVEL_LOW_FROM:
        return "LOW"
    if score >= config.LEVEL_MEDIUM_FROM:
        return "MEDIUM"
    return "HIGH"


def _company_age_years(registration_date: str | None) -> float:
    if not registration_date:
        return 0
    return (date.today() - date.fromisoformat(registration_date)).days / 365.25


def _rating_points(rating: int) -> int:
    raw = (rating - 500) * config.RATING_WEIGHT
    return int(max(-config.RATING_CAP, min(config.RATING_CAP, raw)))


def score_application(requested_amount: int | None, fns: dict, bki: dict) -> dict:
    """Возвращает балл, уровень риска и список сработавших правил с пояснениями."""
    factors = [{"rule": "base", "points": config.SCORE_BASE, "description": "Базовый балл"}]

    def add(rule, points, description):
        factors.append({"rule": rule, "points": points, "description": description})

    monthly_revenue = fns.get("revenue_monthly_avg") or 0
    points, description = _points_for(monthly_revenue, config.REVENUE_STEPS)
    add("revenue", points, description)

    age = _company_age_years(fns.get("registration_date"))
    points, description = _points_for(age, config.AGE_STEPS)
    add("company_age", points, description)

    if bki.get("has_overdue_last_12m"):
        overdue_count = bki.get("overdue_count_last_12m", 0)
        max_days = bki.get("max_overdue_days", 0)
        add(
            "bki_overdue",
            config.POINTS_BKI_OVERDUE,
            f"Просрочки в БКИ за последний год: {overdue_count} (до {max_days} дн.)",
        )

    rating = bki.get("credit_rating")
    if rating is not None:
        add("bki_rating", _rating_points(rating), f"Кредитный рейтинг БКИ: {rating} из 1000")

    if bki.get("active_loans", 0) > config.MANY_LOANS_THRESHOLD:
        add("many_loans", config.POINTS_MANY_LOANS, f"Много действующих кредитов: {bki['active_loans']}")

    arrears = fns.get("tax_arrears", 0)
    if arrears > 0:
        add("tax_arrears", config.POINTS_TAX_ARREARS, f"Задолженность по налогам: {arrears:,} ₽".replace(",", " "))

    stop_reason = config.STOP_LIST_INDUSTRIES.get(fns.get("industry_code"))
    if stop_reason:
        add("stop_industry", config.POINTS_STOP_INDUSTRY, f"Отрасль из стоп-листа: {stop_reason}")

    annual_revenue = fns.get("revenue_last_12m") or monthly_revenue * 12
    if requested_amount and annual_revenue:
        points, description = _points_for(requested_amount / annual_revenue, config.LOAD_STEPS)
        if points:
            add("load", points, description)

    total = sum(factor["points"] for factor in factors)
    score = max(config.SCORE_MIN, min(config.SCORE_MAX, total))
    # Стоп-лист - жёсткое ограничение: уровень риска не зависит от баллов.
    level = "HIGH" if stop_reason else level_for(score)
    return {
        "risk_score": score,
        "risk_level": level,
        "factors": [f for f in factors if f["points"] != 0 or f["rule"] == "base"],
        "hard_stop": bool(stop_reason),
    }
