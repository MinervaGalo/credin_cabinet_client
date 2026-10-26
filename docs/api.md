# API

Полный список методов и схем доступен в Swagger: http://localhost:8000/docs. Ниже перечислены основные методы.

Все запросы, кроме каталога продуктов и входа, требуют заголовок `Authorization: Bearer <токен>`. Токен выдаёт `POST /api/auth/login`.

## Формат ошибок

Ошибки всегда приходят в одном виде, тексты написаны для предпринимателя:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Проверьте, пожалуйста, заполнение формы",
    "hint": null,
    "fields": [{ "field": "requested_amount", "message": "Для продукта «Оборотный» можно запросить не более 15 000 000 ₽" }]
  }
}
```

## Общие методы

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/auth/login` | Вход, возвращает токен |
| GET | `/api/me` | Профиль текущего пользователя |
| GET | `/api/products` | Каталог кредитных продуктов |
| GET | `/api/companies/lookup/{inn}` | Название компании по ИНН |
| POST | `/api/ai/assistant` | ИИ-ассистент подбора кредита |

## Клиент

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/applications` | Мои заявки, поиск параметром `q` |
| POST | `/api/applications/validate` | Проверка полей без сохранения |
| POST | `/api/applications` | Создать черновик |
| PATCH | `/api/applications/{id}` | Сохранить шаг мастера |
| GET | `/api/applications/{id}` | Заявка целиком |
| POST | `/api/applications/{id}/submit` | Отправить в банк |
| POST | `/api/applications/{id}/accept` | Принять предложение банка |
| POST | `/api/applications/{id}/sign` | Подписать договор |
| GET | `/api/applications/{id}/history` | Хронология |
| POST | `/api/applications/{id}/documents` | Загрузить документ |
| GET | `/api/documents` | Все мои документы |
| GET | `/api/documents/{id}/download` | Скачать документ |
| POST | `/api/documents/{id}/parse` | Разобрать отчётность |
| GET | `/api/notifications` | Последние события |

## Кабинет банка

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/bank/stats` | Карточки дашборда |
| GET | `/api/bank/applications` | Очередь, фильтр `status`, поиск `q` |
| GET | `/api/bank/applications/{id}` | Карточка: скоринг, данные ФНС и БКИ, резюме, аудит |
| POST | `/api/bank/applications/{id}/approve` | Одобрить |
| POST | `/api/bank/applications/{id}/counter-offer` | Встречное предложение |
| POST | `/api/bank/applications/{id}/reject` | Отказать, причина обязательна |
| POST | `/api/bank/applications/{id}/request-documents` | Запросить документы |
| POST | `/api/bank/applications/{id}/rerun-scoring` | Пересчитать скоринг |
| GET | `/api/bank/applications/{id}/history` | Аудит |

## Mock-service

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/mock/fns/{inn}` | Данные ЕГРЮЛ и ФНС |
| GET | `/mock/bki/{inn_or_snils}` | Кредитная история |
| GET | `/mock/scenarios` | Тестовые ИНН и ожидаемые исходы |
