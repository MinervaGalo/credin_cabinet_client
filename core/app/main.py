import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, errors
from .db import run_migrations
from .routers import applications, bank, public
from .seed import seed

logging.basicConfig(level=logging.INFO)
logging.getLogger("transitions").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    run_migrations()
    if config.SEED_ON_START:
        seed()
    yield


app = FastAPI(
    title="Умный кредитный кабинет - API",
    description=(
        "Backend кредитного конвейера для МСБ: мастер заявки, конечный автомат статусов, скоринг + решение, "
        "кабинет банка с аудитом, ИИ-ассистент.\n\n"
        "**Демо-вход:** `anna@example.test` / `demo123` (клиент), `analyst@bank.test` / `demo123` (сотрудник банка). "
        "Получите токен в `POST /api/auth/login` и нажмите «Authorize»."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
errors.install(app)
app.include_router(public.router)
app.include_router(applications.router)
app.include_router(bank.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# Фронт раздаётся тем же сервисом, поэтому страницы и API живут на одном адресе.
frontend_dir = Path(config.FRONTEND_DIR)
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
