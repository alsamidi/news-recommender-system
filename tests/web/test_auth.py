"""Auth behaviour: registration, login, logout, CSRF, session isolation."""
from __future__ import annotations

import re

import pytest

from tests.web.conftest import TEST_PASSWORD, csrf_of
from web.throttle import IP_MAX_FAILURES, MAX_FAILURES


def test_register_creates_user_and_redirects_to_onboarding(client, register):
    """TEST-AC-010 (amended by PRD addendum v1.2 §6).

    Registration now lands on the optional topic screen, which sits between
    the form and the feed. The screen is skippable and shown once, so the feed
    is still one click away; `test_onboarding_*` covers that contract.
    """
    r = register()
    assert r.status_code == 303
    assert r.headers["location"] == "/onboarding/topik"
    assert client.cookies.get("session")


def test_duplicate_email_rejected(client, register):
    register()
    client.cookies.clear()
    r = register(email="budi@example.com")
    assert r.status_code == 400                  # TEST-AC-011
    assert "Email sudah terdaftar." in r.text


def test_short_password_rejected(client):
    page = client.get("/register")
    r = client.post("/register", data={
        "name": "X", "email": "x@example.com", "password": "pendek",
        "password_confirm": "pendek", "csrf_token": csrf_of(page.text)})
    assert r.status_code == 400                  # TEST-AC-014
    assert "minimal 8" in r.text


def test_password_confirmation_mismatch(client):
    page = client.get("/register")
    r = client.post("/register", data={
        "name": "X", "email": "x@example.com", "password": TEST_PASSWORD,
        "password_confirm": "berbeda123", "csrf_token": csrf_of(page.text)})
    assert r.status_code == 400                  # TEST-AC-013
    assert "tidak sama" in r.text


def test_password_stored_hashed(client, register):
    register()
    row = client.app.state.store.get_user_by_email("budi@example.com")
    assert row["password_hash"].startswith("scrypt$")   # TEST-AC-012
    assert TEST_PASSWORD not in row["password_hash"]


def test_session_token_stored_hashed(client, register):
    register()
    cookie = client.cookies.get("session")
    with client.app.state.store.connect() as conn:
        rows = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert len(rows) == 1
    assert rows[0]["token_hash"] != cookie              # TEST-AC-019


def test_login_success_and_uniform_failure(client, register):
    register()
    client.cookies.clear()
    page = client.get("/login")
    token = csrf_of(page.text)

    bad = client.post("/login", data={"email": "budi@example.com",
                                      "password": "salah", "csrf_token": token})
    ghost = client.post("/login", data={"email": "nobody@example.com",
                                        "password": "salah", "csrf_token": token})
    assert bad.status_code == ghost.status_code == 400
    assert "Email atau password salah." in bad.text
    assert "Email atau password salah." in ghost.text    # TEST-AC-016

    ok = client.post("/login", data={"email": "budi@example.com",
                                     "password": TEST_PASSWORD, "csrf_token": token},
                     follow_redirects=False)
    assert ok.status_code == 303                          # TEST-AC-015


def test_csrf_missing_is_rejected(client):
    page = client.get("/register")
    r = client.post("/register", data={
        "name": "X", "email": "x@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD})
    assert r.status_code == 403                           # TEST-AC-021


def test_logout_destroys_session(client, register):
    register()
    session_token = client.cookies.get("session")
    page = client.get("/")
    token = csrf_of(page.text)
    r = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303                           # TEST-AC-017
    client.cookies.set("session", session_token)
    assert client.get("/", follow_redirects=False).status_code == 303


def test_protected_pages_require_session(client):
    for path in ["/", "/histori", "/berita/N52622"]:
        assert client.get(path, follow_redirects=False).status_code == 303  # TEST-AC-020


def test_cookie_flags(client, register):
    """Session cookie must be HttpOnly and SameSite=Lax (TEST-AC-018)."""
    register()
    cookie = next(c for c in client.cookies.jar if c.name == "session")
    rest = {k.lower(): v for k, v in cookie._rest.items()}
    assert "httponly" in rest
    assert str(rest.get("samesite", "")).lower() == "lax"


def test_session_expiry_is_enforced(client, register):
    """An expired session must not authenticate (TEST-AC-022, 7-day TTL)."""
    register()
    token = client.cookies.get("session")
    store = client.app.state.store
    with store.connect() as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    client.cookies.set("session", token)
    assert client.get("/", follow_redirects=False).status_code == 303
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"] == 0


def test_csrf_rejects_self_supplied_cookie(client):
    """An attacker-planted cookie pair must not pass (SEC finding)."""
    client.cookies.set("csrf_nonce", "attacker-nonce")
    r = client.post("/register", data={
        "name": "Evil", "email": "evil@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        "csrf_token": "1700000000.deadbeef"})
    assert r.status_code == 403


def test_csrf_token_is_bound_to_its_nonce(client):
    """A valid token replayed against a different nonce must be rejected."""
    page = client.get("/register")
    token = csrf_of(page.text)
    client.cookies.set("csrf_nonce", "different-nonce")
    r = client.post("/register", data={
        "name": "X", "email": "x@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD, "csrf_token": token})
    assert r.status_code == 403


def test_csrf_rejects_tampered_signature(client):
    page = client.get("/register")
    token = csrf_of(page.text)
    ts, _mac = token.split(".", 1)
    r = client.post("/register", data={
        "name": "X", "email": "x@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD, "csrf_token": f"{ts}.{'0' * 64}"})
    assert r.status_code == 403


def test_session_csrf_differs_from_presession(client, register):
    """Logged-in POSTs validate against the session token, not the nonce."""
    register()
    session_token = next(c for c in client.cookies.jar if c.name == "session")
    client.cookies.clear()
    client.cookies.set("session", session_token.value)
    r = client.post("/logout", data={"csrf_token": "bogus"})
    assert r.status_code == 403


def test_login_throttled_after_five_failures(client, register):
    """ARCHITECTURE §6: 5 failures per email per 15 minutes."""
    register()
    client.cookies.clear()
    token = csrf_of(client.get("/login").text)
    for _ in range(5):
        r = client.post("/login", data={"email": "budi@example.com",
                                        "password": "salah", "csrf_token": token})
        assert r.status_code == 400
    blocked = client.post("/login", data={"email": "budi@example.com",
                                          "password": "salah", "csrf_token": token})
    assert blocked.status_code == 429
    assert "Terlalu banyak percobaan" in blocked.text


def test_throttle_does_not_affect_other_emails(client, register):
    register()
    client.cookies.clear()
    token = csrf_of(client.get("/login").text)
    for _ in range(5):
        client.post("/login", data={"email": "budi@example.com",
                                    "password": "salah", "csrf_token": token})
    other = client.post("/login", data={"email": "nobody@example.com",
                                        "password": "salah", "csrf_token": token})
    assert other.status_code == 400          # still evaluated, not blocked


def test_successful_login_resets_failures(client, register):
    register()
    client.cookies.clear()
    token = csrf_of(client.get("/login").text)
    for _ in range(4):
        client.post("/login", data={"email": "budi@example.com",
                                    "password": "salah", "csrf_token": token})
    ok = client.post("/login", data={"email": "budi@example.com",
                                     "password": TEST_PASSWORD, "csrf_token": token},
                     follow_redirects=False)
    assert ok.status_code == 303
    assert not client.app.state.throttle.is_blocked("budi@example.com")


def test_throttle_window_expires():
    """Unit-level: failures age out of the window."""
    from web.throttle import LoginThrottle
    t = LoginThrottle(window_seconds=1, max_failures=2)
    t.record_failure("a@x.com")
    t.record_failure("a@x.com")
    assert t.is_blocked("a@x.com")
    assert t.retry_after("a@x.com") >= 1
    import time
    time.sleep(1.1)
    assert not t.is_blocked("a@x.com")


def test_csrf_token_survives_a_clock_tick(client):
    """A rendered token must not expire just because a second passed.

    Regression: the middleware used to re-sign a fresh token on every GET,
    so a form held open across a clock tick posted a stale signature (403).
    """
    import time

    token = csrf_of(client.get("/login").text)
    time.sleep(1.2)
    r = client.post("/login", data={"email": "a@example.com",
                                    "password": "salah", "csrf_token": token})
    assert r.status_code == 400, r.status_code


def test_csrf_token_is_stable_across_gets(client):
    """Two GETs of the same form must render the same token."""
    first = csrf_of(client.get("/login").text)
    second = csrf_of(client.get("/register").text)
    assert first == second


def test_landing_page_accessible_for_guests_and_redirects_if_logged_in(client, register):
    """Landing page is open to guests with CTAs; redirects authenticated users to /."""
    r = client.get("/landing")
    assert r.status_code == 200
    assert "Berita Terpilih Sesuai Minatmu" in r.text
    assert "/register" in r.text
    assert "/login" in r.text

    # When authenticated, visiting /landing redirects to /
    register()
    r = client.get("/landing", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_per_ip_throttle_stops_cross_account_guessing(client, register):
    """One attacker, many emails: the per-email key cannot see this.

    Per-email limiting lets an attacker try one password against a thousand
    accounts. The per-IP key exists to stop exactly that.
    """
    app = client.app
    app.state.throttle._failures.clear()
    app.state.ip_throttle._failures.clear()

    token = csrf_of(client.get("/login").text)
    # Fail against distinct emails so the per-email counter never trips.
    for i in range(IP_MAX_FAILURES):
        r = client.post("/login", data={"email": f"nobody{i}@example.com",
                                        "password": "salah", "csrf_token": token})
        assert r.status_code == 400, f"attempt {i} should not be blocked yet"

    blocked = client.post("/login", data={"email": "another@example.com",
                                          "password": "salah", "csrf_token": token})
    assert blocked.status_code == 429
    assert "Terlalu banyak" in blocked.text


def test_per_ip_budget_is_looser_than_per_email(client):
    """A shared address must not lock out bystanders.

    Thirty users behind one campus NAT: five people mistype a few times each,
    and nobody should be locked out, because no single account was attacked.
    """
    app = client.app
    app.state.throttle._failures.clear()
    app.state.ip_throttle._failures.clear()

    # 25 failures spread over 25 accounts from one IP: under the IP budget.
    for i in range(25):
        app.state.ip_throttle.record_failure("10.0.0.7")
    assert not app.state.ip_throttle.is_blocked("10.0.0.7")
    # The per-email counter is what protects an individual account.
    assert IP_MAX_FAILURES > MAX_FAILURES


def test_client_ip_ignores_forwarded_header(client):
    """X-Forwarded-For is caller-controlled; trusting it defeats the limiter."""
    from web.routes.auth import client_ip

    class Req:
        headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        client = type("C", (), {"host": "203.0.113.9"})()

    assert client_ip(Req()) == "203.0.113.9"


def test_secure_flag_follows_configuration(monkeypatch):
    """WEB_SECURE_COOKIES must actually reach set_cookie, default off."""
    import importlib

    from web import config as cfgmod

    monkeypatch.delenv("WEB_SECURE_COOKIES", raising=False)
    assert cfgmod.load_config().secure_cookies is False
    monkeypatch.setenv("WEB_SECURE_COOKIES", "1")
    assert cfgmod.load_config().secure_cookies is True
    monkeypatch.setenv("WEB_SECURE_COOKIES", "nonsense")
    with pytest.raises(ValueError):
        cfgmod.load_config()


def test_csrf_secret_comes_from_configuration(monkeypatch):
    """A fixed secret keeps anonymous tokens valid across restarts/workers."""
    from web import config as cfgmod

    monkeypatch.delenv("WEB_CSRF_SECRET", raising=False)
    assert cfgmod.load_config().csrf_secret is None
    monkeypatch.setenv("WEB_CSRF_SECRET", "a-fixed-secret")
    assert cfgmod.load_config().csrf_secret == "a-fixed-secret"


def test_logout_is_idempotent(client, register):
    """Logging out twice must not produce a CSRF error.

    A double click, a refresh of the POST, or a tab left open from before a
    re-login all arrive with a token whose session no longer exists. The user
    asked to be logged out; that state already holds. The old code fell
    through to the anonymous CSRF branch and answered 403 with a raw JSON
    body, which is what a user reported seeing.
    """
    register()
    feed = client.get("/").text
    token = re.search(r'action="/logout".*?value="([^"]+)"', feed, re.S).group(1)

    first = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert first.status_code == 303

    second = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert second.status_code == 303
    assert second.headers["location"] == "/login"


def test_logout_still_requires_csrf_when_a_session_exists(client, register):
    """Idempotency must not become "logout accepts any token".

    A forged token against a live session is still rejected; only the
    no-session case short-circuits.
    """
    register()
    r = client.post("/logout", data={"csrf_token": "bogus"}, follow_redirects=False)
    assert r.status_code == 403
    # The session survives the rejected request.
    assert client.get("/", follow_redirects=False).status_code == 200


def test_csrf_error_renders_a_page_not_json(client):
    """A browser must not be handed {"detail": ...} for a form failure."""
    r = client.post("/register", data={
        "name": "X", "email": "x@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD}, headers={"accept": "text/html"})
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()
    assert "CSRF token tidak valid" in r.text


def test_csrf_error_still_json_for_api_clients(client):
    """The frozen API's error shape is unchanged by the web-layer handler."""
    r = client.post("/recommend", json={"top_k": 999})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/json")
    assert "detail" in r.json()

# ---------------------------------------------------------------------------
# Persona feature removal (v1.3)
# ---------------------------------------------------------------------------

def test_persona_endpoints_are_gone(client):
    """TEST-AC-250 / TEST-AC-271: the persona feature was deleted, not hidden.

    It existed to demo a warm feed for a dataset account. v1.3 removes roles
    entirely: the routes must 404 (not 403/405), and the login page must not
    advertise them.
    """
    assert client.get("/login/persona", follow_redirects=False).status_code == 404
    r = client.post("/login/persona", data={"persona_user_id": "x"},
                    follow_redirects=False)
    assert r.status_code == 404
    # "personalisasi" is product copy, not the removed feature: match the
    # feature's own words, not the substring.
    login = client.get("/login").text.lower()
    assert "persona dataset" not in login
    assert "/login/persona" not in login


def test_config_has_no_persona_fields():
    """TEST-AC-271: the config surface no longer carries persona knobs."""
    from web.config import load_config

    cfg = load_config()
    for attr in ("persona_user_id", "persona_email", "persona_password",
                 "persona_picker", "persona_picker_limit"):
        assert not hasattr(cfg, attr), attr
