import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    MOCK_SERVICE_URL="inprocess",
    UPLOAD_DIR=f"{_tmp}/uploads",
    FRONTEND_DIR="/nonexistent",
    SEED_ON_START="1",
)

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # lifespan -> seed()
        yield c


def _login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "demo123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def anna(client):
    return _login(client, "anna@example.test")


@pytest.fixture(scope="session")
def analyst(client):
    return _login(client, "analyst@bank.test")
