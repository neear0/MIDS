from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="efaktura-test-"))
os.environ["EFAKTURA_DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["EFAKTURA_SCHEMATRON_DIR"] = str(_tmp / "no-schematron")
os.environ["EFAKTURA_EXTRACTION_PROVIDER"] = "heuristic"
os.environ.pop("EFAKTURA_ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.factories import COMPANY  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    from app import models  # noqa: F401
    from app.peppol import access_point

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    access_point._mock_singleton = None
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


def register(client: TestClient, email: str = "jana@example.sk") -> dict:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "tajneheslo1",
                                                       "full_name": "Jana"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def auth(client: TestClient) -> dict:
    return register(client)


@pytest.fixture
def company_id(client: TestClient, auth: dict) -> int:
    resp = client.post("/api/v1/companies", json=COMPANY, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
