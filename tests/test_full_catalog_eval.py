"""Tests for full-catalog evaluation helpers (pure functions only)."""
import numpy as np


def test_minmax_basic():
    from evaluation.full_catalog_eval import _minmax
    out = _minmax(np.array([2.0, 4.0, 6.0]))
    assert np.allclose(out, [0.0, 0.5, 1.0])


def test_minmax_constant_returns_zeros():
    from evaluation.full_catalog_eval import _minmax
    out = _minmax(np.array([3.0, 3.0, 3.0]))
    assert np.allclose(out, [0.0, 0.0, 0.0])


def test_metrics_hand_computed():
    # recommended = [a(hit@1), x(miss), b(hit@3)], relevant = {a, b, c}, k = 3
    # P = 2/3; R = 2/3; AP = (1/1 + 2/3)/min(3,3) = (1+0.6667)/3 = 0.5556
    # DCG = 1/log2(2) + 0 + 1/log2(4) = 1.0 + 0.5 = 1.5
    # ideal = [1,1,1] -> IDCG = 1 + 1/log2(3) + 0.5 = 2.13093; NDCG = 1.5/2.13093
    from evaluation.full_catalog_eval import _metrics_at_ks
    got = _metrics_at_ks(["a", "x", "b"], {"a", "b", "c"}, [3])
    assert abs(got["precision@3"] - 2 / 3) < 1e-9
    assert abs(got["recall@3"] - 2 / 3) < 1e-9
    assert abs(got["map@3"] - ((1.0 + 2 / 3) / 3)) < 1e-9
    assert abs(got["ndcg@3"] - (1.5 / (1.0 + 1 / np.log2(3) + 0.5))) < 1e-9


def test_metrics_ideal_length_exactly_k():
    # len(relevant)=5 > k=3, ideal must be [1,1,1] not [1]*5.
    # actual=[hit,miss,miss]: DCG=1.0, IDCG=1+1/log2(3)+0.5 -> NDCG=1/2.13093
    from evaluation.full_catalog_eval import _metrics_at_ks
    got = _metrics_at_ks(["a", "x", "y"], {"a", "b", "c", "d", "e"}, [3])
    assert abs(got["ndcg@3"] - (1.0 / (1.0 + 1 / np.log2(3) + 0.5))) < 1e-9
    assert abs(got["map@3"] - ((1.0 / 1) / 3)) < 1e-9


def test_topk_selects_exact_kmax_sorted():
    from evaluation.full_catalog_eval import _topk_sorted
    s = np.array([0.1, 0.9, 0.5, 0.7, 0.3])
    assert _topk_sorted(s, 3) == [1, 3, 2]
