"""Единый формат ошибок с понятными для предпринимателя формулировками."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Бизнес-ошибка: code - для программы, message/hint - для человека."""

    def __init__(
        self, message: str, status: int = 400, code: str = "error", hint: str | None = None, fields: list | None = None
    ):
        self.message, self.status, self.code, self.hint, self.fields = message, status, code, hint, fields or []


def body(code: str, message: str, hint: str | None = None, fields: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "hint": hint, "fields": fields or []}}


# Названия полей для сообщений об ошибках разбора запроса.
_FIELD_NAMES = {
    "amount": "Сумма кредита",
    "requested_amount": "Сумма кредита",
    "term_months": "Срок",
    "inn": "ИНН",
    "company_name": "Название компании",
    "product_id": "Кредитный продукт",
    "purpose": "Цель финансирования",
    "email": "Email",
    "password": "Пароль",
    "full_name": "Имя",
    "comment": "Комментарий",
    "reason": "Причина",
}


def _humanize(err: dict) -> dict:
    loc = [str(x) for x in err["loc"] if x not in ("body", "query", "path")]
    field = loc[-1] if loc else "body"
    name = _FIELD_NAMES.get(field, field)
    kind = err["type"]
    if kind == "missing":
        msg = f"Поле «{name}» обязательно для заполнения"
    elif kind in ("int_parsing", "float_parsing", "int_from_float"):
        msg = f"В поле «{name}» нужно указать число, например 3000000"
    elif kind.startswith("string_too_short"):
        msg = f"Поле «{name}» заполнено слишком коротко"
    elif kind == "string_pattern_mismatch":
        msg = f"В поле «{name}» укажите значение в нужном формате, например name@example.com"
    elif kind == "json_invalid":
        msg = "Не удалось прочитать данные формы. Обновите страницу и попробуйте ещё раз"
    else:
        msg = f"Проверьте поле «{name}»: {err.get('msg', 'некорректное значение')}"
    return {"field": field, "message": msg}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return JSONResponse(body(e.code, e.message, e.hint, e.fields), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        fields = [_humanize(x) for x in e.errors()]
        return JSONResponse(
            body("validation_error", "Проверьте, пожалуйста, заполнение формы", fields=fields), status_code=422
        )

    @app.exception_handler(HTTPException)
    async def _http(_: Request, e: HTTPException):
        texts = {401: "Нужно войти в кабинет", 403: "У вас нет доступа к этому разделу", 404: "Ничего не найдено"}
        return JSONResponse(
            body("http_%d" % e.status_code, texts.get(e.status_code) or str(e.detail)), status_code=e.status_code
        )
