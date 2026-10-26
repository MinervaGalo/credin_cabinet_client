"""Параметры системы: пороги и веса скоринга, правила решения, настройки окружения."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./credit.db")
# Значение "inprocess" запускает мок внутри процесса, это нужно тестам.
MOCK_SERVICE_URL = os.getenv("MOCK_SERVICE_URL", "http://localhost:8001")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USE_CELERY = os.getenv("USE_CELERY", "0") == "1"  # иначе конвейер идёт фоновой задачей FastAPI
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
FRONTEND_DIR = os.getenv("FRONTEND_DIR", "../frontend")
SEED_ON_START = os.getenv("SEED_ON_START", "1") == "1"

SECRET_KEY = os.getenv("SECRET_KEY", "demo-secret-change-me")
TOKEN_TTL_HOURS = 12

# Тестовые ИНН из макета не проходят контрольную сумму, поэтому по умолчанию это предупреждение.
VALIDATE_INN_CHECKSUM = False
MIN_AMOUNT = 100_000
MIN_REQUIRED_DOC_TYPES: list[str] = []

SCORE_MIN, SCORE_MAX = 0, 1000
SCORE_BASE = 400

# Пороги проверяются сверху вниз, срабатывает первый подходящий.
REVENUE_STEPS = [
    (10_000_000, +150, "Выручка более 10 млн ₽ в месяц"),
    (3_000_000, +100, "Выручка 3–10 млн ₽ в месяц"),
    (1_000_000, +50, "Выручка 1–3 млн ₽ в месяц"),
    (0, -30, "Выручка менее 1 млн ₽ в месяц"),
]
AGE_STEPS = [
    (3, +60, "Компания работает более 3 лет"),
    (1, +30, "Компания работает 1–3 года"),
    (0, -40, "Компания работает менее года"),
]
LOAD_STEPS = [
    (0.50, -80, "Запрошенная сумма превышает 50% годовой выручки"),
    (0.25, -40, "Запрошенная сумма превышает 25% годовой выручки"),
]
POINTS_BKI_OVERDUE = -250
POINTS_TAX_ARREARS = -100
POINTS_MANY_LOANS = -50
POINTS_STOP_INDUSTRY = -400
MANY_LOANS_THRESHOLD = 3
STOP_LIST_INDUSTRIES = {"92.00": "Деятельность по организации азартных игр и заключению пари"}

# Рейтинг БКИ даёт (рейтинг - 500) * RATING_WEIGHT баллов, но не больше RATING_CAP по модулю.
RATING_WEIGHT = 0.2
RATING_CAP = 100

LEVEL_LOW_FROM = 650
LEVEL_MEDIUM_FROM = 450

# Средний риск при балле от этого порога даёт встречное предложение, ниже - ручную проверку.
AUTO_COUNTER_MIN_SCORE = 550
COUNTER_AMOUNT_FACTOR = 0.8
COUNTER_RATE_ADD = 1.5

OLLAMA_URL = os.getenv("OLLAMA_URL", "")  # пустое значение отключает LLM, работают правила
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TIMEOUT = 25
