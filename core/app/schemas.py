from pydantic import BaseModel, Field

from . import config


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=config.MIN_PASSWORD_LENGTH)
    full_name: str = Field(min_length=2)
    inn: str | None = None
    company_name: str | None = None


class ApplicationIn(BaseModel):
    """Все поля необязательны: так работает режим мастера и сохранение черновика."""

    product_id: int | None = None
    requested_amount: int | None = None
    term_months: int | None = None
    purpose: str | None = None
    inn: str | None = None
    company_name: str | None = None


class CompanyIn(BaseModel):
    inn: str
    name: str = Field(min_length=2)


class DecisionIn(BaseModel):
    amount: int | None = None
    rate: float | None = None
    comment: str | None = None


class RejectIn(BaseModel):
    reason: str = Field(min_length=3)


class CommentIn(BaseModel):
    comment: str = Field(min_length=3)


class AssistantIn(BaseModel):
    message: str = Field(min_length=2)
