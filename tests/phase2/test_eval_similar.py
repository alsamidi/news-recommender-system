"""Tests for src/phase2/eval_similar.py and its evidence JSON.

Deliberately cheap: the CLI itself loads the TF-IDF recommender (~19s) and
scores 300 queries (~50s), which has no place in the unit suite. Here we only
check the two things that can regress silently and cheaply:

  * the query sample is reproducible and well-formed (pure function), and
  * the committed evidence JSON keeps its schema and its headline claim
    (TF-IDF beats the random baseline on category match).

The JSON assertions double as a guard against a hand-edited or stale artifact:
if someone re-runs the CLI and the lift disappears, this test fails.
"""
import json
from pathlib import Path

import pytest

from src.phase2.eval_similar import draw_sample

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/evidence/phase2/similar_eval.json"

# Six metric keys the evidence JSON is contracted to carry.
METRIC_KEYS = (
    "category_match@5",
    "coview_recall@5",
    "coview_recall@5_threshold_1",
    "random_baseline_category_match@5",
    "category_match@5_lift_over_random",
    "coview_coverage_queries_with_any_coview_candidate",
)

TOP_CATEGORIES = 8


# ---------------------------------------------------------------------------
# sample determinism (pure function, no I/O beyond the given frame)
# ---------------------------------------------------------------------------

def _toy_frame(n=1000):
    """Sorted nid pool standing in for TRAIN-viewed catalog nids."""
    return [f"I{i:010x}" for i in range(n)]


def test_draw_sample_is_deterministic():
    pool = _toy_frame()
    a = draw_sample(pool, 300, 42)
    b = draw_sample(pool, 300, 42)
    assert a == b, "same seed must reproduce the same sample"
    # a different seed must actually move the sample
    assert draw_sample(pool, 300, 7) != a


def test_draw_sample_shape_and_frame():
    pool = _toy_frame()
    sample = draw_sample(pool, 300, 42)
    assert len(sample) == 300
    assert len(set(sample)) == 300, "sample must be unique (no replacement)"
    assert sample == sorted(sample), "sample must be sorted for determinism"
    assert set(sample) <= set(pool), "must draw only from the input frame"


def test_draw_sample_rejects_oversized_request():
    with pytest.raises(ValueError):
        draw_sample(_toy_frame(10), 300, 42)


# ---------------------------------------------------------------------------
# evidence JSON schema
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def evidence():
    assert EVIDENCE.exists(), f"missing evidence artifact: {EVIDENCE}"
    return json.loads(EVIDENCE.read_text())


def test_evidence_top_level_schema(evidence):
    for key in ("protocol", "metrics", "by_category", "generated_at_utc"):
        assert key in evidence, f"missing top-level key {key!r}"
    assert evidence["generated_at_utc"], "generated_at_utc must be non-empty"


def test_protocol_pins_the_measured_contract(evidence):
    protocol = evidence["protocol"]
    assert protocol["k"] == 5
    assert protocol["n_queries"] == 300
    assert protocol["sample_seed"] == 42
    # the threshold must be stated, not implied
    assert protocol["coview_threshold"] == 2
    assert protocol["coview_threshold_variant"] == 1


def test_metrics_keys_present_and_in_unit_range(evidence):
    metrics = evidence["metrics"]
    for key in METRIC_KEYS:
        assert key in metrics, f"missing metric {key!r}"
        value = metrics[key]
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        assert 0.0 <= value <= 1.0, f"{key}={value} outside [0, 1]"


def test_tfidf_beats_random_baseline(evidence):
    """The one claim the block's quality rests on: it is not a random picker."""
    metrics = evidence["metrics"]
    assert metrics["category_match@5"] > metrics["random_baseline_category_match@5"]


def test_by_category_breakdown_shape(evidence):
    by_category = evidence["by_category"]
    assert len(by_category) == TOP_CATEGORIES
    for cat, row in by_category.items():
        assert isinstance(cat, str) and cat
        for key in ("n_queries", "category_match@5",
                    "random_baseline_category_match@5"):
            assert key in row, f"{cat!r} missing {key!r}"
        assert row["n_queries"] > 0
        assert 0.0 <= row["category_match@5"] <= 1.0
        assert 0.0 <= row["random_baseline_category_match@5"] <= 1.0
