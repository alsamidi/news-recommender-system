"""Full-catalog / cold-start item evaluation (Day 4).

Table A = restricted ALS item space (3,394 items).
Table B = full catalog (93,698 items, TF-IDF transform-only, no leakage).
Metric formulas are verbatim copies of the frozen day-4 evaluator in
src/models/hybrid/train.py:evaluate_hybrid. Do NOT change them.
"""
import numpy as np


def _minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = x.min(), x.max()
    if hi <= lo:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def _topk_sorted(scores: np.ndarray, kmax: int) -> list:
    top = np.argpartition(-scores, kmax - 1)[:kmax]
    top = top[np.argsort(-scores[top])]
    return top.tolist()


def _metrics_at_ks(recommended: list, relevant: set, k_values: list) -> dict:
    out = {}

    def dcg(rels):
        return sum(r / np.log2(i + 2) for i, r in enumerate(rels))

    for k in k_values:
        rec_k = recommended[:k]
        hits = sum(1 for r in rec_k if r in relevant)
        out[f"precision@{k}"] = hits / k if k > 0 else 0
        out[f"recall@{k}"] = hits / len(relevant) if relevant else 0
        ap, hc = 0, 0
        for i, r in enumerate(rec_k):
            if r in relevant:
                hc += 1
                ap += hc / (i + 1)
        out[f"map@{k}"] = ap / min(len(relevant), k) if relevant else 0
        ideal = sorted([1] * min(len(relevant), k) + [0] * max(0, k - len(relevant)), reverse=True)
        actual = [1 if r in relevant else 0 for r in rec_k]
        out[f"ndcg@{k}"] = dcg(actual) / dcg(ideal) if dcg(ideal) > 0 else 0
    return out


def main():
    raise NotImplementedError


if __name__ == "__main__":
    main()
