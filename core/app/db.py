from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

_kwargs = (
    {"connect_args": {"check_same_thread": False}}
    if config.DATABASE_URL.startswith("sqlite")
    else {"pool_pre_ping": True}
)
engine = create_engine(config.DATABASE_URL, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Приводит схему базы к последней версии. Повторный вызов безопасен."""
    core_dir = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(core_dir / "alembic.ini")), "head")
