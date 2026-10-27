import numpy as np
import pandas as pd
import pytest

from src.phase2.split import draft_q80


def _events(times):
    return pd.DataFrame({
        "dummy_user_id": [f"u{i%3}" for i in range(len(times))],
        "nid": [f"I{i:04d}" for i in range(len(times))],
        "event": "view",
        "occurred_at": pd.to_datetime(times, utc=True),
    })


def test_draft_q80_basic():
    # 10 events on 10 consecutive days: p80 (linear) = index 7.2 ->
    # between day 8 (index 7) and day 9 (index 8)
    t = pd.date_range("2025-01-01", periods=10, freq="D", tz="UTC")
    cut = draft_q80(_events(t))
    assert t[7] < cut < t[8]


def test_draft_q80_unsorted_input_is_sorted():
    t = pd.date_range("2025-01-01", periods=10, freq="D", tz="UTC")
    shuffled = _events(t[::-1])
    assert draft_q80(shuffled) == draft_q80(_events(t))


def test_draft_q80_single_event_returns_that_time():
    cut = draft_q80(_events(pd.Series(["2025-06-01T12:00:00Z"])))
    assert cut == pd.Timestamp("2025-06-01 12:00:00+00:00")


def test_split_catalog_membership():
    # train = published <= cutoff; dev = after (catalog-level rule from plan)
    cut = pd.Timestamp("2025-09-18 06:05", tz="UTC")
    meta = pd.DataFrame({
        "nid": ["A", "B", "C"],
        "published_at": pd.to_datetime(
            ["2025-01-01", "2025-09-18 06:05", "2025-09-19"],
            format="mixed", utc=True),
    })
    train = meta[meta["published_at"] <= cut]
    dev = meta[meta["published_at"] > cut]
    assert set(train["nid"]) == {"A", "B"}
    assert set(dev["nid"]) == {"C"}
