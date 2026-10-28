"""Tests for src/phase2/eval_session.py and its evidence JSON.

Deliberately cheap: the CLI retrains ALS on all nine sensitivity points
(~10-15 min), which has no place in the unit suite. Here we only check what
can regress silently:

  * the committed evidence JSON keeps its schema and its headline claim,
  * `means.warm_user` still equals the mean of models/indo_eval.json
    ndcg@10.als (the official number must not drift), and
  * the per-point grid is the locked 9-cell seed x s grid.

If someone re-runs the CLI and the served path stops being the worse path,
this test fails — the JSON is not allowed to become a stale artifact.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/evidence/phase2/session_path_eval.json"
OFFICIAL = REPO / "models/indo_eval.json"

RANKINGS = ("warm_user", "session_hybrid", "session_als_only", "popularity")
SEEDS = (1, 2, 3)
S_GRID = (0.9, 1.1, 1.3)
TOL = 1e-9


@pytest.fixture(scope="module")
def evidence():
    assert EVIDENCE.exists(), f"missing evidence artifact: {EVIDENCE}"
    return json.loads(EVIDENCE.read_text())


@pytest.fixture(scope="module")
def official():
    assert OFFICIAL.exists(), f"missing official evaluation: {OFFICIAL}"
    return json.loads(OFFICIAL.read_text())


def test_top_level_schema(evidence):
    for key in ("protocol", "means", "per_point", "generated_at_utc"):
        assert key in evidence, f"missing top-level key {key!r}"
    assert evidence["generated_at_utc"], "generated_at_utc must be non-empty"
    assert len(evidence["per_point"]) == 9


def test_means_are_floats_in_unit_range(evidence):
    means = evidence["means"]
    for name in RANKINGS:
        assert name in means, f"missing ranking {name!r} in means"
        value = means[name]
        assert isinstance(value, float), f"means[{name!r}] is not a float"
        assert 0.0 < value < 1.0, f"means[{name!r}]={value} outside (0, 1)"


def test_warm_user_mean_matches_official_eval(evidence, official):
    """The official number must not drift: warm path == indo_eval.json."""
    ref = [float(p["ndcg@10"]["als"]) for p in official["per_point"]]
    expected = sum(ref) / len(ref)
    assert evidence["means"]["warm_user"] == pytest.approx(expected, abs=TOL)


def test_warm_user_per_point_matches_official_eval(evidence, official):
    ref = {(int(p["seed"]), round(float(p["s"]), 6)): float(p["ndcg@10"]["als"])
           for p in official["per_point"]}
    for point in evidence["per_point"]:
        key = (int(point["seed"]), round(float(point["s"]), 6))
        assert key in ref, f"point {key} missing from indo_eval.json"
        assert point["warm_user"] == pytest.approx(ref[key], abs=TOL)


def test_per_point_grid_is_the_locked_nine_cells(evidence):
    got = sorted((int(p["seed"]), round(float(p["s"]), 6))
                 for p in evidence["per_point"])
    want = sorted((seed, round(s, 6)) for seed in SEEDS for s in S_GRID)
    assert got == want


def test_every_point_carries_all_rankings(evidence):
    for point in evidence["per_point"]:
        for name in RANKINGS:
            assert name in point, f"point missing ranking {name!r}"
            assert isinstance(point[name], float)
            assert 0.0 <= point[name] < 1.0


def test_served_path_scores_below_the_warm_path(evidence):
    """Headline claim: the served session path scores below the warm path."""
    means = evidence["means"]
    assert means["session_hybrid"] < means["warm_user"]


def test_cbf_blend_is_what_drags_the_session_path_down(evidence):
    """alpha=0.8 costs the session path; the session ALS profile alone does not.

    The cold session profile at alpha=1.0 scores at or above the warm user
    vector on the mean, so the drop the web app serves comes from the 0.2
    CBF weight, not from the missing per-account factor.
    """
    means = evidence["means"]
    assert means["session_hybrid"] < means["session_als_only"]
    assert means["session_als_only"] > means["warm_user"]
    for point in evidence["per_point"]:
        assert point["session_hybrid"] < point["session_als_only"]


def test_protocol_pins_the_measured_contract(evidence):
    protocol = evidence["protocol"]
    assert protocol["metric"] == "NDCG@10"
    assert protocol["points"] == 9
    assert protocol["alpha"] == 0.8
    assert protocol["window"] == 50
    assert protocol["n_accounts"] == [600]
    assert protocol["seeds"] == list(SEEDS)
    assert protocol["s_grid"] == list(S_GRID)
