"""Temporal split utilities for the Indo corpus interactions.

The cutoff is drafted as the 80th-percentile event time BEFORE the Gate C
 ALS loop, but is only LOCKED (committed to the lock) after Gate C passes —
after which generator parameters may not change without resetting
evaluation.
"""
import pandas as pd


def draft_q80(interactions: pd.DataFrame) -> pd.Timestamp:
    """80th-percentile event time (deterministic, exclusive-less p80).

    Uses linear interpolation over sorted occurred_at; returns tz-aware UTC.
    """
    t = pd.to_datetime(interactions["occurred_at"], utc=True).sort_values()
    pos = 0.80 * (len(t) - 1)
    lo = int(pos)
    frac = pos - lo
    t_lo = t.iloc[lo]
    if lo + 1 >= len(t):
        return pd.Timestamp(t_lo)
    t_hi = t.iloc[lo + 1]
    return t_lo + (t_hi - t_lo) * frac


CATALOG_SPLIT_COLS = ["nid", "title", "content", "processed_text",
                      "category", "source", "published_at", "split"]


def split_interactions(interactions: pd.DataFrame, cutoff: pd.Timestamp):
    """Temporal split of interactions on occurred_at (stable order)."""
    t = pd.to_datetime(interactions["occurred_at"], utc=True)
    order = interactions.assign(_t=t).sort_values("_t", kind="mergesort")
    train = order[order["_t"] <= cutoff].drop(columns="_t")
    dev = order[order["_t"] > cutoff].drop(columns="_t")
    return train.reset_index(drop=True), dev.reset_index(drop=True)


def split_catalog(catalog: pd.DataFrame, cutoff: pd.Timestamp):
    """Catalog split: train = published <= cutoff, dev = after.

    Articles without interactions keep their frozen catalog rows: they stay
    in the TF-IDF catalog but never enter CF as items (no factors by
    construction — CF items come from the train interactions matrix).
    """
    pub = pd.to_datetime(catalog["published_at"], utc=True)
    train = catalog[pub <= cutoff].copy()
    dev = catalog[pub > cutoff].copy()
    train["split"] = "train"
    dev["split"] = "dev"
    return train.reset_index(drop=True), dev.reset_index(drop=True)
