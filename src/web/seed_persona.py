"""Create or update the demo persona account. Idempotent.

Usage:
    python -m src.web.seed_persona

Requires (see .env.example):
    WEB_DEMO_PERSONA_USER_ID   dataset user that HAS ALS factors
    WEB_DEMO_PERSONA_EMAIL     local login email
    WEB_DEMO_PERSONA_PASSWORD  local password (never committed)

Re-running updates the existing account instead of creating a duplicate.
The persona id is verified against the frozen API before anything is written.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from .config import load_config  # noqa: E402
from .db import Store  # noqa: E402
from .security import hash_password  # noqa: E402


def main() -> int:
    cfg = load_config()
    missing = [
        name for name, value in (
            ("WEB_DEMO_PERSONA_USER_ID", cfg.persona_user_id),
            ("WEB_DEMO_PERSONA_EMAIL", cfg.persona_email),
            ("WEB_DEMO_PERSONA_PASSWORD", cfg.persona_password),
        ) if not value
    ]
    if missing:
        print("Persona seed skipped; missing: " + ", ".join(missing), file=sys.stderr)
        return 2

    # Verify the dataset user actually has ALS factors before writing anything.
    import api.main as frozen

    rec = frozen.load_recommender()
    if cfg.persona_user_id not in rec._d["user_map"]:
        print(
            f"Persona {cfg.persona_user_id!r} has no ALS factors "
            f"(not in the {len(rec._d['user_map'])} eligible users). Aborting.",
            file=sys.stderr,
        )
        return 3

    store = Store(cfg.db_path)
    store.init_schema()
    user_id = store.upsert_persona(
        name="Demo Dataset",
        email=cfg.persona_email,
        password_hash=hash_password(cfg.persona_password),
        persona_user_id=cfg.persona_user_id,
    )
    print(f"persona ready: user_id={user_id} email={cfg.persona_email} "
          f"dataset_user={cfg.persona_user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
