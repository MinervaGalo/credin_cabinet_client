"""Окружение Alembic: адрес базы и метаданные моделей берутся из приложения."""

from alembic import context
from sqlalchemy import create_engine

from app import (  # noqa: F401  (импорт моделей регистрирует таблицы в метаданных)
    config,
    models,
)
from app.db import Base

target_metadata = Base.metadata
is_sqlite = config.DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=is_sqlite
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(config.DATABASE_URL)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=is_sqlite)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
