# Сторонние компоненты

Проект использует только открытое ПО. Лицензии указаны по состоянию на момент сборки - перед публикацией сверьтесь с актуальными версиями.

## Python-библиотеки (core и mock)

| Пакет | Назначение | Лицензия |
|---|---|---|
| FastAPI | веб-фреймворк, OpenAPI/Swagger | MIT |
| Starlette | ASGI-основа FastAPI, тестовый клиент | BSD-3-Clause |
| Pydantic | валидация данных | MIT |
| Uvicorn | ASGI-сервер | BSD-3-Clause |
| SQLAlchemy | ORM | MIT |
| psycopg 3 | драйвер PostgreSQL | LGPL-3.0 |
| transitions | конечный автомат кредитного конвейера | MIT |
| Celery | фоновые задачи | BSD-3-Clause |
| redis-py | клиент Redis | MIT |
| httpx | HTTP-клиент (вызовы мок-сервиса, Ollama) | BSD-3-Clause |
| python-multipart | загрузка файлов | Apache-2.0 |
| pypdf | извлечение текста из PDF | BSD-3-Clause |
| pytest | тесты | MIT |

## Инфраструктура (Docker-образы)

| Образ | Лицензия |
|---|---|
| postgres:16-alpine | PostgreSQL License |
| redis:7-alpine | зависит от версии образа: до 7.2 - BSD-3-Clause, с 7.4 - RSALv2 / SSPLv1, с 8.0 добавлена AGPLv3. Для хакатона подходит; для коммерческого использования проверьте условия или замените на Valkey (BSD-3-Clause) |
| ollama/ollama (необязательно, профиль `ai`) | MIT |

## Модели ИИ (необязательно)

ИИ-функции работают и без модели (rule-based режим). Если включена локальная LLM:

| Модель | Веса | Лицензия |
|---|---|---|
| Qwen2.5-1.5B-Instruct (по умолчанию, `OLLAMA_MODEL=qwen2.5:1.5b`) | открытые | Apache-2.0 |

Другие открытые модели (например, `qwen2.5:7b` - Apache-2.0, `llama3.2:3b` - Llama 3.2 Community License) подключаются сменой `OLLAMA_MODEL`. Условия использования проверьте на странице модели.

## Фронтенд и документация

| Компонент | Лицензия |
|---|---|
| Шрифт Inter (подключается из Google Fonts в `styles.css`) | SIL Open Font License 1.1 |
| Mermaid (генерация диаграмм в `docs/`, в рантайме не используется) | MIT |
