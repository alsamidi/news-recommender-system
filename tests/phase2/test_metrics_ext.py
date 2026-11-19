"""Hand-computed tests for the notebook metrics module (goal: eval metrics).

The locked evaluator (src/phase2/evaluate.py) already carries hand-computed
cases for ndcg/ap/recall; this file does the same for the two metrics the
comparison notebook adds (Precision@K, F1@K) and pins the AP@10 == MAP@10
alias that the cross-check against models/indo_eval.json relies on.

All expected values below are computed by hand in the same style as
test_evaluate.py::test_metric_math_hand_computed.
"""
import pytest

from src.phase2.evaluate import ap_at_k
from notebooks.metrics_ext import METRICS, f1_at_k, map_at_k, precision_at_k

RANKED = ["x1", "x2", "x3", "x4", "x5"]
REL = {"x2", "x4"}

RANKED2 = ["x1", "z1", "z2", "x2", "z3", "z4", "z5", "z6", "z7", "z8"]
REL2 = {"x2", "x9"}


def test_precision_at_k_hand_computed():
    # 2 of the top-5 are relevant -> 2/5
    assert precision_at_k(RANKED, REL, 5) == pytest.approx(0.4)
    # cutoff above the only relevant hit in ranked2 -> 1/10
    assert precision_at_k(RANKED2, REL2, 10) == pytest.approx(0.1)
    # cutoff below any hit -> 0, not an error
    assert precision_at_k(RANKED2, REL2, 2) == 0.0


def test_recall_at_k_hand_computed():
    # both relevant items sit inside the top-5 -> 2/2
    assert f1_at_k.__module__  # keep import alive; recall itself is locked
    from src.phase2.evaluate import recall_at_k
    assert recall_at_k(RANKED, REL, 5) == pytest.approx(1.0)
    assert recall_at_k(RANKED2, REL2, 10) == pytest.approx(0.5)


def test_f1_at_k_hand_computed():
    # P@5=0.4, R@5=1.0 -> F1 = 2*0.4*1.0/(0.4+1.0) = 4/7
    assert f1_at_k(RANKED, REL, 5) == pytest.approx(4 / 7)
    # P@10=0.1, R@10=0.5 -> F1 = 2*0.05/0.6 = 1/6
    assert f1_at_k(RANKED2, REL2, 10) == pytest.approx(1 / 6)
    # |relevant| < K: ranked=[x1,x2], rel={x1}, k=2 -> P=0.5, R=1 -> 2/3
    assert f1_at_k(["x1", "x2"], {"x1"}, 2) == pytest.approx(2 / 3)


def test_f1_at_k_zero_hits_is_zero_not_nan():
    # nothing retrieved is relevant: harmonic mean is undefined -> 0.0,
    # matching the locked evaluator's all-zero score for no-hit rankings.
    assert f1_at_k(["z1", "z2", "z3"], {"x1"}, 3) == 0.0
    assert f1_at_k([], {"x1"}, 3) == 0.0


def test_map_alias_equals_ap_at_k():
    # the alias must be the identical function result, not a reimplementation:
    # the JSON cross-check against models/indo_eval.json relies on it.
    for ranked, rel in ((RANKED, REL), (RANKED2, REL2)):
        for k in (1, 5, 10):
            assert map_at_k(ranked, rel, k) == ap_at_k(ranked, rel, k)


def test_metrics_registry_has_the_five_names():
    # the notebook and the comparison JSON iterate this registry; a rename
    # here would silently change the JSON schema.
    assert set(METRICS) == {"precision", "recall", "f1", "map", "ndcg"}
