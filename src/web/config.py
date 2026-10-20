"""Web-layer configuration (env-overridable, no secrets in source)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Repository root: src/web/config.py -> src/web -> src -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # fail loudly, never silently fall back
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Config:
    db_path: Path
    session_ttl_days: int
    history_limit: int
    feed_limit: int
    rec_top_k: int
    artifact_config: str
    persona_user_id: str | None
    persona_email: str | None
    persona_password: str | None

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_days * 24 * 60 * 60


def load_config() -> Config:
    """Build config from the environment.

    Defaults match the approved decisions: 7-day sessions, 50-item history
    window, 10 rendered cards, top_k=30 requested from the API.
    """
    db_raw = os.environ.get("WEB_DB_PATH", "data/web.db")
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path

    persona_id = (os.environ.get("WEB_DEMO_PERSONA_USER_ID") or "").strip() or None
    persona_email = (os.environ.get("WEB_DEMO_PERSONA_EMAIL") or "").strip() or None
    persona_password = os.environ.get("WEB_DEMO_PERSONA_PASSWORD") or None

    cfg = Config(
        db_path=db_path,
        session_ttl_days=_int("WEB_SESSION_TTL_DAYS", 7),
        history_limit=_int("WEB_HISTORY_LIMIT", 50),
        feed_limit=_int("WEB_FEED_LIMIT", 10),
        rec_top_k=_int("WEB_REC_TOP_K", 30),
        artifact_config=os.environ.get("WEB_ARTIFACT_CONFIG", "configs/hybrid.yaml"),
        persona_user_id=persona_id,
        persona_email=persona_email,
        persona_password=persona_password,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.session_ttl_days < 1:
        raise ValueError("WEB_SESSION_TTL_DAYS must be >= 1")
    if not 1 <= cfg.history_limit <= 400:
        # 400 is the measured point where serving latency stays flat.
        raise ValueError("WEB_HISTORY_LIMIT must be within 1..400")
    if not 1 <= cfg.feed_limit <= 10:
        raise ValueError("WEB_FEED_LIMIT must be within 1..10")
    if not 1 <= cfg.rec_top_k <= 100:
        # API contract: top_k is 1..100.
        raise ValueError("WEB_REC_TOP_K must be within 1..100")
    if cfg.rec_top_k < cfg.feed_limit:
        raise ValueError("WEB_REC_TOP_K must be >= WEB_FEED_LIMIT")
