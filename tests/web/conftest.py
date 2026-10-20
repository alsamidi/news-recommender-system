"""Shared fixtures for the web-layer tests.

The recommender is loaded once per session (~6 s, ~500 MB). Tests share one
app and one SQLite file, and an autouse fixture truncates the tables between
tests so each case starts clean.
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

import pytest

# Generated per test session. Tests only need a consistent value within a run,
# so there is no reason to keep a credential-shaped literal in the source.
TEST_PASSWORD = secrets.token_urlsafe(16)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
for p in (str(SRC), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)


REQUIRED_ARTIFACTS = (
    REPO / "data/processed/news_processed.parquet",
    REPO / "data/processed/interactions_train.parquet",
    REPO / "models/als_model.pkl",
    REPO / "models/tfidf_baseline.pkl",
)


def artifacts_available() -> bool:
    return all(p.exists() for p in REQUIRED_ARTIFACTS)


requires_artifacts = pytest.mark.skipif(
    not artifacts_available(),
    reason="research artifacts absent (gitignored); run the full suite where they exist",
)


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from web.app import create_app

    if not artifacts_available():
        pytest.skip("research artifacts absent; web app cannot start without the model")

    db = tmp_path_factory.mktemp("webdb") / "web.db"
    os.environ["WEB_DB_PATH"] = str(db)
    for var in ("WEB_DEMO_PERSONA_USER_ID", "WEB_DEMO_PERSONA_EMAIL",
                "WEB_DEMO_PERSONA_PASSWORD"):
        os.environ.pop(var, None)

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state(request):
    """Empty application tables and cookies before every test.

    Depends on `client` only for tests that actually request it, so pure-logic
    tests still run on a clean checkout with no research artifacts.
    """
    if "client" not in request.fixturenames:
        yield
        return
    client = request.getfixturevalue("client")
    store = client.app.state.store
    with store.connect() as conn:
        conn.execute("DELETE FROM interactions")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM users")
    # Throttle state lives on the app, not in the DB: reset it explicitly.
    client.app.state.throttle._failures.clear()
    client.cookies.clear()
    yield


def csrf_of(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf token missing from form"
    return m.group(1)


@pytest.fixture()
def register(client):
    def _register(name="Budi", email="budi@example.com", password=TEST_PASSWORD):
        page = client.get("/register")
        token = csrf_of(page.text)
        return client.post(
            "/register",
            data={"name": name, "email": email, "password": password,
                  "password_confirm": password, "csrf_token": token},
            follow_redirects=False,
        )
    return _register
