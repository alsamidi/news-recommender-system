"""Full-catalog hybrid inference (Day 6 application layer).

Serving counterpart of the frozen Day 4/5 evaluators. Scoring reuses the
evaluator primitives verbatim (same functions, not copies):

- warm user  = precompute-style profile + expand_cf_scores + mask + top-k,
  mirroring sweep_table_b in evaluation/full_catalog_eval.py;
- cold session = TF-IDF session profile + pseudo-user ALS factor,
  mirroring sweep_cold in evaluation/stratified_eval.py.

Final alpha = 0.4 (Table B full-catalog winner, models/full_catalog_eval.json).
Only the serving default lives here; frozen artifacts are never retrained.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/

import numpy as np
import yaml

from evaluation.full_catalog_eval import (
    _minmax,
    _topk_sorted,
    expand_cf_scores,
    load_all,
)
from evaluation.stratified_eval import pseudo_user_factor

FINAL_ALPHA = 0.4
CATALOG_SIZE = 93698


class UnknownUserError(ValueError):
    """Raised when a warm-user lookup has no ALS user factor (use session API)."""


def serving_alpha(config_path: str = "configs/hybrid.yaml") -> float:
    """Single source of truth for the serving alpha (config file)."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    alpha = float(cfg["model"]["content_weight"])
    assert abs(alpha + float(cfg["model"]["cf_weight"]) - 1.0) < 1e-9, \
        "content_weight + cf_weight must equal 1.0"
    return alpha


class HybridRecommender:
    """Full-catalog (93,698 items) hybrid recommender over frozen artifacts."""

    def __init__(self, data: dict, alpha: float = FINAL_ALPHA):
        assert len(data["full_nids"]) == CATALOG_SIZE, \
            f"catalog {len(data['full_nids'])} != {CATALOG_SIZE}"
        self._d = data
        self.alpha = float(alpha)
        news = data["news"]
        self._titles = news["title"].tolist()
        self._categories = news["category"].tolist()
        self._subcategories = news["subcategory"].tolist()
        pos: dict = {}
        for i, n in enumerate(data["full_nids"]):
            pos.setdefault(n, []).append(i)
        self._pos_of_nid = pos

    def _mask_seen(self, scores: np.ndarray, seen_nids: set) -> None:
        """Mask every position of seen nids (nid-level, stricter than eval).

        The frozen evaluator masks train/session *positions* only, so the
        other-split row of a seen article stays recommendable (and can even
        score a hit). Serving masks all rows of seen nids instead — standard
        already-liked filtering (cf. filter_already_liked in configs/als.yaml).
        Scoring pipeline and alpha are untouched; only the mask set differs.
        """
        mask = [p for n in seen_nids for p in self._pos_of_nid.get(n, [])]
        scores[mask] = -np.inf

    @classmethod
    def load(cls, config_path: str = "configs/hybrid.yaml",
             alpha: float | None = None) -> "HybridRecommender":
        return cls(load_all(),
                   alpha=serving_alpha(config_path) if alpha is None else alpha)

    # -- internals (mirror the evaluators op-for-op) ---------------------

    def _content_norm(self, full_idx_sorted: list) -> np.ndarray:
        full_tfidf = self._d["full_tfidf"]
        prof = full_tfidf[full_idx_sorted].mean(axis=0)
        raw = np.asarray(prof @ full_tfidf.T).ravel()
        return _minmax(raw).astype(np.float32)

    def _cf_norm(self, user_factor: np.ndarray) -> np.ndarray:
        raw = user_factor @ self._d["item_factors"].T
        return _minmax(raw).astype(np.float32)

    def _select(self, scores: np.ndarray, top_k: int) -> list:
        """Evaluator top-k positions, deduped by nid for presentation.

        The catalog stacks train+dev rows, so 28,460 nids occupy two
        positions. Scoring and order follow the evaluator verbatim
        (positions); only presentation collapses duplicates, keeping the
        best-ranked position per nid. Each nid occurs at most 2x, hence
        scanning 2*top_k positions always yields top_k unique nids.
        """
        n_full = len(self._d["full_nids"])
        rec = _topk_sorted(np.asarray(scores), min(2 * top_k, n_full))
        seen, out = set(), []
        for i in rec:
            nid = self._d["full_nids"][i]
            if nid not in seen:
                seen.add(nid)
                out.append(i)
            if len(out) == top_k:
                break
        return out

    def _decorate(self, rec: list, scores: np.ndarray) -> list:
        nids = self._d["full_nids"]
        return [{"nid": nids[i], "title": self._titles[i],
                 "category": self._categories[i],
                 "subcategory": self._subcategories[i],
                 "score": float(scores[i])} for i in rec]

    # -- public API -------------------------------------------------------

    def recommend_user(self, user_id: str, top_k: int = 10,
                       alpha: float | None = None) -> list:
        """Warm user: full train history as mask + TF-IDF profile.

        Identical op order to sweep_table_b for a single alpha.
        """
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        user_map = self._d["user_map"]
        if user_id not in user_map:
            raise UnknownUserError(
                f"user {user_id!r} has no ALS factor (no train history); "
                "use recommend_session instead")
        a = self.alpha if alpha is None else float(alpha)
        ti = self._d["train_full"][user_id]
        c_norm = self._content_norm(sorted(ti))
        cf_norm = self._cf_norm(self._d["user_factors"][user_map[user_id]])
        cf_full = expand_cf_scores(cf_norm, self._d["als_full_pos"],
                                   len(self._d["full_nids"]), a)
        s = a * c_norm + (1 - a) * cf_full
        self._mask_seen(s, {self._d["full_nids"][i] for i in ti})
        rec = self._select(s, top_k)
        return self._decorate(rec, s)

    def recommend_session(self, session_nids: list, top_k: int = 10,
                          alpha: float | None = None) -> list:
        """Cold/session input: history nids as mask + session profile.

        Identical op order to sweep_cold's hybrid branch. When no session
        item exists in ALS space, CF cannot be formed and the request falls
        back to pure content (same scores as the evaluator's content row).
        """
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if not session_nids:
            raise ValueError("session_nids must be non-empty")
        n2f = self._d["nid_to_full"]
        ti = {n2f[n] for n in session_nids if n in n2f}
        if not ti:
            raise ValueError("no session item found in catalog")
        a = self.alpha if alpha is None else float(alpha)
        n_full = len(self._d["full_nids"])
        c_norm = self._content_norm(sorted(ti))
        pu = pseudo_user_factor(list(session_nids), self._d["item_map"],
                                self._d["item_factors"])
        if pu is None:
            s = c_norm.astype(np.float64).copy()
        else:
            cf_full = np.zeros(n_full, dtype=np.float64)
            cf_full[self._d["als_full_pos"]] = self._cf_norm(pu)
            s = a * c_norm.astype(np.float64) + (1 - a) * cf_full
        self._mask_seen(s, {n for n in session_nids if n in n2f})
        rec = self._select(s, top_k)
        return self._decorate(rec, s)

    def similar(self, nid: str, top_k: int = 10) -> list:
        """Content-based neighbours of one catalog item (full TF-IDF cosine).

        All positions sharing the query nid are masked (train+dev rows of
        the same article would otherwise rank top with similarity ~1.0).
        """
        n2f = self._d["nid_to_full"]
        if nid not in n2f:
            raise KeyError(f"item {nid!r} not in catalog")
        full_tfidf = self._d["full_tfidf"]
        i = n2f[nid]
        sims = (full_tfidf[i] @ full_tfidf.T).toarray().ravel()
        same = [j for j, n in enumerate(self._d["full_nids"]) if n == nid]
        sims[same] = -np.inf
        rec = self._select(sims, top_k)
        return self._decorate(rec, sims)

    def article(self, nid: str) -> dict:
        n2f = self._d["nid_to_full"]
        if nid not in n2f:
            raise KeyError(f"item {nid!r} not in catalog")
        i = n2f[nid]
        row = self._d["news"].iloc[i]
        return {"nid": nid, "title": row["title"], "abstract": row["abstract"],
                "category": row["category"], "subcategory": row["subcategory"]}


if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser(description="Smoke-test full-catalog hybrid inference")
    p.add_argument("--user", default=None, help="warm user_id (e.g. from behaviors.tsv)")
    p.add_argument("--session", default=None, help="comma-separated nids for cold session")
    p.add_argument("--top-k", type=int, default=5)
    args = p.parse_args()

    rec = HybridRecommender.load()
    print(f"alpha={rec.alpha} catalog={len(rec._d['full_nids'])}")
    if args.user:
        out = rec.recommend_user(args.user, top_k=args.top_k)
    elif args.session:
        out = rec.recommend_session(args.session.split(","), top_k=args.top_k)
    else:
        p.error("pass --user or --session")
    print(json.dumps(out, indent=2, ensure_ascii=False))
