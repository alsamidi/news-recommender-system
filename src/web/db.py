"""SQLite storage for the web layer.

Owns only application data: users, sessions, interactions. The research catalog
stays in Parquet and is never written here.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL,
    password_hash   TEXT    NOT NULL,
    persona_user_id TEXT,
    created_at      TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
    ON users (lower(email));

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT    NOT NULL UNIQUE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    csrf_token TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

CREATE TABLE IF NOT EXISTS interactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    nid        TEXT    NOT NULL,
    event      TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    source     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interactions_user_time
    ON interactions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_user_nid
    ON interactions (user_id, nid);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Thin SQLite wrapper. One connection per request is fine at this scale."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)

    # -- connection -----------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        """Idempotent schema creation. Safe to run on every startup."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, iso(utcnow())),
            )

    # -- users ----------------------------------------------------------
    def create_user(self, name: str, email: str, password_hash: str,
                    persona_user_id: str | None = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, persona_user_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, email.lower(), password_hash, persona_user_id, iso(utcnow())),
            )
            return int(cur.lastrowid)

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE lower(email) = ?", (email.lower(),)
            ).fetchone()

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    def upsert_persona(self, name: str, email: str, password_hash: str,
                       persona_user_id: str) -> int:
        """Idempotent: re-running must not create a second persona account."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE lower(email) = ?", (email.lower(),)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET name = ?, password_hash = ?, persona_user_id = ?"
                    " WHERE id = ?",
                    (name, password_hash, persona_user_id, row["id"]),
                )
                return int(row["id"])
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, persona_user_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, email.lower(), password_hash, persona_user_id, iso(utcnow())),
            )
            return int(cur.lastrowid)

    # -- sessions -------------------------------------------------------
    def unique_readers(self, nids: list[str]) -> dict[str, int]:
        """nid -> number of distinct accounts that opened it, in this app.

        Unique users, not views: the same person opening an article twice
        counts once. Chunked because SQLite caps host parameters at 999 and a
        feed page can ask about more nids than that.
        """
        if not nids:
            return {}
        out: dict[str, int] = {}
        unique = list(dict.fromkeys(nids))
        for start in range(0, len(unique), 500):
            chunk = unique[start:start + 500]
            placeholders = ",".join("?" * len(chunk))
            with self.connect() as conn:
                rows = conn.execute(
                    f"SELECT nid, COUNT(DISTINCT user_id) AS n"
                    f" FROM interactions WHERE nid IN ({placeholders})"
                    f" GROUP BY nid",
                    chunk,
                ).fetchall()
            for row in rows:
                out[row["nid"]] = int(row["n"])
        return out

    def get_user_by_persona(self, persona_user_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE persona_user_id = ?", (persona_user_id,)
            ).fetchone()

    def ensure_persona_user(self, persona_user_id: str) -> int:
        """Return a local account bound to this dataset user, creating it once.

        Used by the passwordless picker. The password hash is random and never
        handed out: this account is entered by choosing it, not by typing a
        credential, so there is nothing to guess.
        """
        existing = self.get_user_by_persona(persona_user_id)
        if existing is not None:
            return int(existing["id"])
        email = f"{persona_user_id.lower()}@persona.local"
        row = self.get_user_by_email(email)
        if row is not None:
            # Account predates the persona binding (e.g. seeded by hand).
            with self.connect() as conn:
                conn.execute(
                    "UPDATE users SET persona_user_id = ? WHERE id = ?",
                    (persona_user_id, row["id"]),
                )
            return int(row["id"])
        from .security import hash_password
        import secrets as _secrets
        return self.upsert_persona(
            name=persona_user_id,
            email=email,
            password_hash=hash_password(_secrets.token_urlsafe(32)),
            persona_user_id=persona_user_id,
        )

    def create_session(self, user_id: int, token_hash: str, csrf_token: str,
                       ttl_seconds: int) -> None:
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, csrf_token)"
                " VALUES (?, ?, ?, ?, ?)",
                (token_hash, user_id, iso(now), iso(now + timedelta(seconds=ttl_seconds)),
                 csrf_token),
            )

    def get_session(self, token_hash: str) -> sqlite3.Row | None:
        """Return a live session, deleting it first if expired."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= iso(utcnow()):
                conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
                return None
            return row

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    # -- interactions ---------------------------------------------------
    def add_view(self, user_id: int, nid: str, source: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO interactions (user_id, nid, event, created_at, source)"
                " VALUES (?, ?, 'view', ?, ?)",
                (user_id, nid, iso(utcnow()), source),
            )

    def history_nids(self, user_id: int, limit: int) -> list[str]:
        """Most recent unique nid values, newest first."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT nid, MAX(created_at) AS last_seen FROM interactions"
                " WHERE user_id = ? GROUP BY nid ORDER BY last_seen DESC, nid ASC"
                " LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [r["nid"] for r in rows]

    def all_history_nids(self, user_id: int) -> set[str]:
        """Every nid the user has ever opened (used to filter the feed)."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT nid FROM interactions WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {r["nid"] for r in rows}

    def history_rows(self, user_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT nid, event, created_at, source FROM interactions"
                " WHERE user_id = ? ORDER BY created_at DESC, id DESC",
                (user_id,),
            ).fetchall()

    def count_interactions(self, user_id: int) -> int:
        with self.connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) AS c FROM interactions WHERE user_id = ?", (user_id,)
            ).fetchone()["c"])
