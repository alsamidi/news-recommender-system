"""Metrics module for the comparison notebook (goal: metric comparison).

Lives next to the notebook so the frozen `src/phase2/` package is imported,
never modified. The rankers come from `src.phase2.evaluate`; this module only
adds the two metrics the locked evaluator does not emit (Precision@K, F1@K)
and the same-name wrappers with @K suffixes that the notebook and the
comparison JSON use.

Every function here is pure and cheap to hand-verify: see
`tests/phase2/test_metrics_ext.py` for the hand-computed cases.
"""
from __future__ import annotations

from src.phase2.evaluate import ap_at_k, ndcg_at_k, recall_at_k


def precision_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the top-k list that is relevant.

    An empty top-k (k <= 0) or empty list yields 0.0 — precision of an empty
    prediction is defined as 0, matching recall_at_k's empty-relevant rule in
    the locked evaluator.
    """
    if k <= 0 or not ranked_ids:
        return 0.0
    top = ranked_ids[:k]
    return sum(1 for nid in top if nid in relevant) / len(top)


def f1_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Harmonic mean of Precision@K and Recall@K at the same cutoff.

    Returns 0.0 when both are 0 (no relevant item retrieved): the harmonic
    mean is undefined there, and 0 is the only value consistent with the
    locked evaluator, which scores a ranking with no hits as 0 on every
    metric.
    """
    p = precision_at_k(ranked_ids, relevant, k)
    r = recall_at_k(ranked_ids, relevant, k)
    if p + r == 0.0:
        return 0.0
    return 2.0 * p * r / (p + r)


def map_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Same quantity as the locked ap_at_k, under the literature name.

    Kept as an explicit alias so the comparison JSON can carry all five
    metric names without a reader having to know that "AP@K" and "MAP@K"
    coincide at a single rank list. The cross-check against
    models/indo_eval.json pins this equivalence numerically.
    """
    return ap_at_k(ranked_ids, relevant, k)


def ndcg(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return ndcg_at_k(ranked_ids, relevant, k)


def recall(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    return recall_at_k(ranked_ids, relevant, k)


METRICS = {
    "precision": precision_at_k,
    "recall": recall,
    "f1": f1_at_k,
    "map": map_at_k,
    "ndcg": ndcg,
}
