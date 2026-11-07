"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile

# Point the app at a throwaway database before it is imported anywhere.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="iksir-test-"), "test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB}")
os.environ.setdefault("SECRET_KEY", "test-secret-key-long-enough-for-hs256-signing")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # keep the suite fast
# The rate limiter is per-process and would otherwise throttle the suite itself:
# every auth_client fixture registers a user, and the auth limit is 10/minute.
os.environ.setdefault("RATE_LIMIT_REQUESTS", "100000")
os.environ.setdefault("AUTH_RATE_LIMIT_REQUESTS", "100000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_client(client):
    """A client with a freshly registered user already signed in."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": "Test Chemist", "password": "correcthorse"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
