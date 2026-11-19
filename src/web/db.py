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

-- PRD addendum v1.2: topic selection for the 0-view feed.
-- `position` is the CANONICAL chip order (the order of TOPIC_LABELS), not the
-- order the user clicked: a plain multi-select form submits in DOM order, so
-- click order is not recoverable without client-side JS, and a stored order
-- that silently disagrees with what the browser sent would make the feed
-- nondeterministic. Same set of chips => same feed, for every user.
CREATE TABLE IF NOT EXISTS user_topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label      TEXT    NOT NULL,
    position   INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, label)
);

CREATE INDEX IF NOT EXISTS idx_user_topics_user ON user_topics (user_id);
"""

# `users.topics_prompted_at` cannot come from CREATE TABLE IF NOT EXISTS on an
# existing database, so it is added by an idempotent migration below.
TOPICS_PROMPTED_COLUMN = ("topics_prompted_at", "TEXT")


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
            self._migrate_users_topics_prompted(conn)
            self._migrate_drop_persona(conn)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, iso(utcnow())),
            )

    @staticmethod
    def _migrate_drop_persona(conn: sqlite3.Connection) -> None:
        """Delete dataset-persona accounts and drop `users.persona_user_id`.

        The persona feature was removed in v1.3 (owner decision): it existed to
        demo a warm feed for a dataset account, and the product no longer has
        roles. Order matters — rows are deleted first so no account keeps a
        binding that would dangle once the column is gone. Both steps are
        guarded, so re-running on an already-migrated database is a no-op.
        """
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "persona_user_id" in cols:
            conn.execute("DELETE FROM users WHERE persona_user_id IS NOT NULL")
            conn.execute("ALTER TABLE users DROP COLUMN persona_user_id")

    @staticmethod
    def _migrate_users_topics_prompted(conn: sqlite3.Connection) -> None:
        """Add `users.topics_prompted_at` to databases created before v1.2.

        `CREATE TABLE IF NOT EXISTS` does nothing on an existing table, so the
        column needs an explicit, idempotent ALTER. Without this marker the
        server cannot tell "never shown the onboarding" from "skipped it", and
        PRD addendum v1.2 C2 promises the screen appears exactly once.
        """
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if TOPICS_PROMPTED_COLUMN[0] not in cols:
            conn.execute(
                f"ALTER TABLE users ADD COLUMN {TOPICS_PROMPTED_COLUMN[0]}"
                f" {TOPICS_PROMPTED_COLUMN[1]}"
            )

    # -- users ----------------------------------------------------------
    def create_user(self, name: str, email: str, password_hash: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, created_at)"
                " VALUES (?, ?, ?, ?)",
                (name, email.lower(), password_hash, iso(utcnow())),
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

    # -- topic preferences (PRD addendum v1.2) --------------------------
    def mark_topics_prompted(self, user_id: int) -> None:
        """Record that the onboarding screen was shown (chosen or skipped)."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET topics_prompted_at = ?"
                " WHERE id = ? AND topics_prompted_at IS NULL",
                (iso(utcnow()), user_id),
            )

    def user_topics(self, user_id: int) -> list[str]:
        """Chosen labels, in canonical chip order."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT label FROM user_topics WHERE user_id = ? ORDER BY position ASC",
                (user_id,),
            ).fetchall()
        return [r["label"] for r in rows]

    def replace_user_topics(self, user_id: int, labels: list[str]) -> None:
        """Replace the user's topics atomically; `labels` must already be
        validated and in canonical order."""
        with self.connect() as conn:
            conn.execute("DELETE FROM user_topics WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT INTO user_topics (user_id, label, position, created_at)"
                " VALUES (?, ?, ?, ?)",
                [(user_id, label, i + 1, iso(utcnow()))
                 for i, label in enumerate(labels)],
            )

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
