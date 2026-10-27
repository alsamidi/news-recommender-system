"""Reader counts for article cards.

Two numbers, deliberately kept apart because they mean different things:

- **dataset readers** — unique dataset accounts in the train+dev
  interactions that viewed this nid. This is a *sample* (50,000 MIND users;
  600 simulated indo accounts), not the article's real readership, so the
  label must say "dataset".
- **app readers** — unique accounts in this deployment that opened the
  article. Small and honest; it starts at zero.

Both are unique-user counts, not click counts: one person opening an article
twice still counts once.

Only a fraction of catalogue nids appear in the interactions at all, so the
dataset figure is absent for most articles. Cards hide a zero rather
than print "0 pembaca", which would claim nobody read it.

Path selection follows the serving era (SERVING_ERA, default indo per
PRD v1.1): the indo parquets key accounts by `dummy_user_id`, normalized
to `user_id` after load so the counting logic below stays shared.
"""
from __future__ import annotations

import os

import pandas as pd

MIND_TRAIN_PATH = "data/processed/interactions_train.parquet"
MIND_DEV_PATH = "data/processed/interactions_dev.parquet"
INDO_TRAIN_PATH = "data/processed/indo/interactions_train.parquet"
INDO_DEV_PATH = "data/processed/indo/interactions_dev.parquet"


def _era_paths() -> tuple[str, str, str]:
    """Train/dev parquet paths + account column for the serving era.

    SERVING_ERA=mind keeps the frozen MIND parquets; anything else (default)
    serves the indo corpus (PRD v1.1). The indo files key accounts by
    `dummy_user_id`, normalized to `user_id` after load so the counting
    logic below stays shared.
    """
    if os.environ.get("SERVING_ERA", "").lower() == "mind":
        return MIND_TRAIN_PATH, MIND_DEV_PATH, "user_id"
    return INDO_TRAIN_PATH, INDO_DEV_PATH, "dummy_user_id"

def build_dataset_readers() -> dict[str, int]:
    """nid -> unique dataset accounts that viewed it, across both splits.

    Built once at startup. Read-only afterwards.
    """
    train_p, dev_p, user_col = _era_paths()
    frames = [
        pd.read_parquet(path, columns=[user_col, "nid"])
        .rename(columns={user_col: "user_id"})
        for path in (train_p, dev_p)
    ]
    both = pd.concat(frames, ignore_index=True)
    counts = both.groupby("nid")["user_id"].nunique()
    return {str(nid): int(n) for nid, n in counts.items()}

def attach_reader_counts(request, rows: list[dict]) -> list[dict]:
    """Add dataset_readers / app_readers to each row, in place, and return it.

    A missing count is left as 0 so the template can hide it.
    """
    if not rows:
        return rows

    nids = [r["nid"] for r in rows if r.get("nid")]
    app_counts = request.app.state.store.unique_readers(nids)
    dataset = request.app.state.dataset_readers

    for row in rows:
        nid = row.get("nid")
        row["dataset_readers"] = dataset.get(nid, 0) if nid else 0
        row["app_readers"] = app_counts.get(nid, 0) if nid else 0
    return rows
