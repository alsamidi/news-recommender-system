"""Reader counts for article cards.

Two numbers, deliberately kept apart because they mean different things:

- **dataset readers** — unique `user_id`s in the MIND train+dev interactions
  that clicked this nid. This is a *sample* of 50,000 users over one period,
  not the article's real readership, so the label must say "dataset".
- **app readers** — unique accounts in this deployment that opened the
  article. Small and honest; it starts at zero.

Both are unique-user counts, not click counts: one person opening an article
twice still counts once.

Only 9,100 of 65,238 catalogue nids appear in the interactions at all (13.9%),
so the dataset figure is absent for most articles. Cards hide a zero rather
than print "0 pembaca", which would claim nobody read it.
"""
from __future__ import annotations

import pandas as pd

TRAIN_PATH = "data/processed/interactions_train.parquet"
DEV_PATH = "data/processed/interactions_dev.parquet"


def build_dataset_readers() -> dict[str, int]:
    """nid -> unique dataset users who clicked it, across both splits.

    Built once at startup (~0.6 s, 9,100 entries). Read-only afterwards.
    """
    frames = [
        pd.read_parquet(path, columns=["user_id", "nid"])
        for path in (TRAIN_PATH, DEV_PATH)
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
