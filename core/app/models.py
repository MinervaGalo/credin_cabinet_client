"""Модель данных."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    ogrn: Mapped[str | None] = mapped_column(String(15))
    name: Mapped[str] = mapped_column(String(255))
    industry_code: Mapped[str | None] = mapped_column(String(10))
    registration_date: Mapped[str | None] = mapped_column(String(10))
    financial_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="client")  # client | analyst
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))


class CreditProduct(Base):
    __tablename__ = "credit_products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(String(100), default="")
    base_rate: Mapped[float] = mapped_column(Float)  # % годовых
    min_sum: Mapped[int] = mapped_column(Integer)
    max_sum: Mapped[int] = mapped_column(Integer)
    min_term: Mapped[int] = mapped_column(Integer)  # месяцев
    max_term: Mapped[int] = mapped_column(Integer)
    risk_rules: Mapped[dict] = mapped_column(JSON, default=dict)  # напр. {"max_risk_level": "MEDIUM"}


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True)  # вида «КР-2026-0148»
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("credit_products.id"))
    requested_amount: Mapped[int | None] = mapped_column(Integer)
    term_months: Mapped[int | None] = mapped_column(Integer)
    purpose: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    decision: Mapped[str | None] = mapped_column(String(20))  # APPROVED | REJECTED | COUNTER_OFFER
    decision_by: Mapped[str | None] = mapped_column(String(20))  # AUTO | MANUAL
    decision_reason: Mapped[str | None] = mapped_column(Text)
    approved_amount: Mapped[int | None] = mapped_column(Integer)
    approved_rate: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    company: Mapped[Company | None] = relationship()
    product: Mapped[CreditProduct | None] = relationship()
    user: Mapped[User] = relationship()
    history: Mapped[list["ApplicationStateHistory"]] = relationship(
        order_by="ApplicationStateHistory.id", cascade="all, delete-orphan"
    )
    enrichment: Mapped[list["EnrichmentData"]] = relationship(
        order_by="EnrichmentData.id", cascade="all, delete-orphan"
    )
    scorings: Mapped[list["ScoringResult"]] = relationship(order_by="ScoringResult.id", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(order_by="Document.id", cascade="all, delete-orphan")


class ApplicationStateHistory(Base):
    """Аудит: каждое изменение статуса и ручное вмешательство."""

    __tablename__ = "application_state_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(100))  # client:email | analyst:email | system
    comment: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EnrichmentData(Base):
    __tablename__ = "enrichment_data"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    source: Mapped[str] = mapped_column(String(10))  # FNS | BKI
    payload_json: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ScoringResult(Base):
    __tablename__ = "scoring_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(10))
    factors_json: Mapped[list] = mapped_column(JSON)  # [{rule, points, description}]
    summary: Mapped[str | None] = mapped_column(Text)  # текстовое пояснение для аналитика
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))  # BALANCE | STATEMENT | INVOICE | OTHER
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(500))  # пусто у демонстрационных документов
    parsed_data_json: Mapped[dict | None] = mapped_column(JSON)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
