from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


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
