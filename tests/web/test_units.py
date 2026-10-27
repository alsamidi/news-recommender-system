"""Pure-logic tests: run on a clean checkout with no research artifacts."""
from __future__ import annotations

import time

import pytest

from web.config import load_config
from web.db import Store
from web.security import (
    csrf_matches, hash_password, new_csrf_token, new_session_token,
    token_hash, verify_password,
)
from web.throttle import LoginThrottle


# --- security ---------------------------------------------------------

def test_hash_is_salted_and_unique():
    a = hash_password("correct horse")
    b = hash_password("correct horse")
    assert a != b, "identical passwords must not produce identical hashes"
    assert a.startswith("scrypt$")
    assert "correct horse" not in a


def test_verify_accepts_correct_and_rejects_wrong():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h) is True
    assert verify_password("wrong horse", h) is False


def test_verify_rejects_malformed_hash():
    for bad in ["", "not-a-hash", "scrypt$x$y$z$q$r", "scrypt$1$2$3$!!!$???"]:
        assert verify_password("anything", bad) is False


def test_empty_password_refused():
    with pytest.raises(ValueError):
        hash_password("")


def test_session_tokens_are_unique_and_hashed():
    t1, t2 = new_session_token(), new_session_token()
    assert t1 != t2
    assert token_hash(t1) != token_hash(t2)
    assert token_hash(t1) != t1
    assert len(token_hash(t1)) == 64


def test_csrf_compare_is_false_on_missing():
    assert csrf_matches(None, "x") is False
    assert csrf_matches("x", None) is False
    assert csrf_matches("", "x") is False
    assert csrf_matches("x", "x") is True
    assert new_csrf_token() != new_csrf_token()


# --- throttle ---------------------------------------------------------

def test_throttle_blocks_at_threshold():
    t = LoginThrottle(window_seconds=60, max_failures=3)
    for _ in range(3):
        t.record_failure("a@x.com")
    assert t.is_blocked("a@x.com")
    assert t.retry_after("a@x.com") >= 1


def test_throttle_isolated_per_key():
    t = LoginThrottle(window_seconds=60, max_failures=1)
    t.record_failure("a@x.com")
    assert t.is_blocked("a@x.com")
    assert not t.is_blocked("b@x.com")


def test_throttle_reset_clears():
    t = LoginThrottle(window_seconds=60, max_failures=1)
    t.record_failure("a@x.com")
    t.reset("a@x.com")
    assert not t.is_blocked("a@x.com")


def test_throttle_window_expiry():
    t = LoginThrottle(window_seconds=1, max_failures=1)
    t.record_failure("a@x.com")
    assert t.is_blocked("a@x.com")
    time.sleep(1.1)
    assert not t.is_blocked("a@x.com")


# --- config -----------------------------------------------------------

def test_config_defaults(monkeypatch):
    for var in ("WEB_SESSION_TTL_DAYS", "WEB_HISTORY_LIMIT", "WEB_FEED_LIMIT",
                "WEB_REC_TOP_K", "WEB_DB_PATH"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.session_ttl_days == 7
    assert cfg.history_limit == 50
    assert cfg.feed_limit == 10
    assert cfg.rec_top_k == 30


def test_config_rejects_top_k_below_feed_limit(monkeypatch):
    monkeypatch.setenv("WEB_REC_TOP_K", "5")
    monkeypatch.setenv("WEB_FEED_LIMIT", "10")
    with pytest.raises(ValueError):
        load_config()


def test_config_rejects_out_of_range_values(monkeypatch):
    monkeypatch.setenv("WEB_FEED_LIMIT", "11")
    with pytest.raises(ValueError):
        load_config()
    monkeypatch.setenv("WEB_FEED_LIMIT", "10")
    monkeypatch.setenv("WEB_REC_TOP_K", "101")
    with pytest.raises(ValueError):
        load_config()


def test_config_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("WEB_SESSION_TTL_DAYS", "seven")
    with pytest.raises(ValueError):
        load_config()


# --- store ------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "unit.db")
    s.init_schema()
    return s


def test_schema_init_is_idempotent(store):
    store.init_schema()
    store.init_schema()
    with store.connect() as conn:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "sessions", "interactions", "user_topics"} <= tables
    # Still absent: preference-as-ratings and derived caches stay out (C5).
    assert "ratings" not in tables
    assert "articles_cache" not in tables


def test_duplicate_email_rejected_case_insensitively(store):
    store.create_user("A", "a@x.com", hash_password("pw12345678"))
    with pytest.raises(Exception):
        store.create_user("B", "A@X.COM", hash_password("pw12345678"))


def test_upsert_persona_is_idempotent(store):
    h = hash_password("pw12345678")
    first = store.upsert_persona("Demo", "demo@x.com", h, "U10045")
    second = store.upsert_persona("Demo", "demo@x.com", h, "U10045")
    assert first == second
    with store.connect() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    assert n == 1


def test_history_nids_unique_newest_first(store):
    uid = store.create_user("A", "a@x.com", hash_password("pw12345678"))
    store.add_view(uid, "N1", "feed")
    store.add_view(uid, "N2", "feed")
    store.add_view(uid, "N1", "feed")
    assert store.history_nids(uid, 10) == ["N1", "N2"]
    assert store.count_interactions(uid) == 3


def test_all_history_nids_covers_full_history(store):
    uid = store.create_user("A", "a@x.com", hash_password("pw12345678"))
    for i in range(60):
        store.add_view(uid, f"N{i}", "direct")
    assert len(store.history_nids(uid, 50)) == 50
    assert len(store.all_history_nids(uid)) == 60


def test_session_expiry_deletes_row(store):
    uid = store.create_user("A", "a@x.com", hash_password("pw12345678"))
    store.create_session(uid, token_hash("tok"), "csrf", ttl_seconds=-1)
    assert store.get_session(token_hash("tok")) is None
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"] == 0


def test_history_isolation_between_users(store):
    a = store.create_user("A", "a@x.com", hash_password("pw12345678"))
    b = store.create_user("B", "b@x.com", hash_password("pw12345678"))
    store.add_view(a, "N1", "feed")
    store.add_view(b, "N2", "feed")
    assert store.all_history_nids(a) == {"N1"}
    assert store.all_history_nids(b) == {"N2"}
