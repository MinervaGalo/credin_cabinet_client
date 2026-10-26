"""Клиент mock-service (ФНС и БКИ). На месте моков в продакшене были бы реальные интеграции."""

import sys
from pathlib import Path

import httpx

from . import config

_inproc = None


def _client():
    global _inproc
    if config.MOCK_SERVICE_URL == "inprocess":  # для тестов: мок запускается внутри процесса
        if _inproc is None:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mock"))
            from fastapi.testclient import TestClient

            from main import app as mock_app

            _inproc = TestClient(mock_app)
        return _inproc, ""
    return httpx.Client(timeout=10), config.MOCK_SERVICE_URL


def _get(path: str) -> dict:
    client, base = _client()
    r = client.get(base + path)
    r.raise_for_status()
    return r.json()


def fetch_fns(inn: str) -> dict:
    return _get(f"/mock/fns/{inn}")


def fetch_bki(inn: str) -> dict:
    return _get(f"/mock/bki/{inn}")
