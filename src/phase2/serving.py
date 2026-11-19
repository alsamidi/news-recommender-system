"""Indo-corpus serving recommender (Task 13) behind the MIND-era interface.

Public surface mirrors `models.hybrid.infer.HybridRecommender` exactly:
  recommend_user(user_id, top_k) / recommend_session(session_nids, top_k) /
  similar(nid, top_k) / article(nid) / attributes .alpha and ._d (the web
  layer reads `_d["user_map" | "train_full" | "full_nids" | "item_map" |
  "nid_to_full"]`).

The served system IS the evaluated system (Task 11, `src/phase2/
evaluate.py`): per user,
  hybrid = alpha * minmax(ALS dot) + (1 - alpha) * minmax(TF-IDF cosine),
min-max over the full catalog, alpha from configs/indo_serving.yaml (0.8,
CF weight of the grid winner). Catalog = full indo catalog (67,381 items,
nid-unique — no train/dev position stacking, so `_select` needs no dedupe);
scoring covers every item: CBF everywhere, ALS where factors exist (floor
-1.0 elsewhere, exactly the evaluated ranker). Popularity ranking (feed
path) = TRAIN view counts desc, nid asc tie-break.
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn.preprocessing as pp
import yaml

_REPO = Path(__file__).resolve().parents[2]


def minmax(v: np.ndarray) -> np.ndarray:
    """Same semantics as the evaluated minmax (evaluate.py)."""
    v = np.asarray(v, dtype=float).copy()
    finite = np.isfinite(v)
    if not finite.any():
        return np.zeros_like(v)
    lo, hi = v[finite].min(), v[finite].max()
    if hi <= lo:
        out = np.zeros_like(v)
        out[finite] = 1.0
        return out
    v = (v - lo) / (hi - lo)
    v[~finite] = 0.0
    return v


def load_config(path: str = "configs/indo_serving.yaml") -> dict:
    with open(_REPO / path) as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]
    assert abs(float(m["cf_weight"]) + float(m["content_weight"]) - 1.0) < 1e-9
    return cfg


from models.hybrid.infer import UnknownUserError as _MindUnknownUserError


class UnknownUserError(_MindUnknownUserError):
    """Indo-era warm-user miss.

    Subclasses the frozen exception so the API route's
    `except UnknownUserError` (imported from models.hybrid.infer) keeps
    catching it — the seam stays schema/route compatible.
    """


class IndoHybridRecommender:
    """Hybrid serving over the indo corpus (full 67,381-item catalog)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        comp = cfg["components"]
        self.alpha = float(cfg["model"]["cf_weight"])  # ALS/CF weight

        catalog = pd.read_parquet(_REPO / comp["catalog_path"])
        self._catalog = catalog
        self.full_nids: list[str] = catalog["nid"].tolist()
        self._nid_pos = {n: i for i, n in enumerate(self.full_nids)}
        self.nid_to_full = dict(self._nid_pos)  # interface alias (1:1 here)

        self._titles = catalog["title"].tolist()
        self._categories = catalog["category"].tolist()
        self._abstracts = catalog["content"].tolist()

        # TF-IDF fit on the TRAIN catalog only, transform full (evaluated rule)
        from sklearn.feature_extraction.text import TfidfVectorizer
        train_cat = pd.read_parquet(_REPO / comp["catalog_train_path"])
        vec = TfidfVectorizer()
        vec.fit(train_cat["processed_text"].fillna("").tolist())
        self._tfidf = pp.normalize(vec.transform(
            catalog["processed_text"].fillna("").tolist()))

        # ALS factors (train interactions only, Gate C)
        with open(_REPO / comp["als_model_path"], "rb") as f:
            model = pickle.load(f)
        self._item_factors = model.item_factors
        self._user_factors = model.user_factors
        train_i = pd.read_parquet(_REPO / comp["interactions_train_path"],
                                  columns=["dummy_user_id", "nid"])
        train_i = train_i[train_i["nid"].isin(self._nid_pos)]
        # factor rows are positional over the CSR of fit time: rebuild the
        # same sorted id orders (train_als.build_csr used sorted uniques)
        self._als_items = sorted(train_i["nid"].unique())
        self._item_row = {n: i for i, n in enumerate(self._als_items)}
        als_users = sorted(train_i["dummy_user_id"].unique())
        self._user_map = {u: i for i, u in enumerate(als_users)}
        self.item_map = self._item_row  # interface alias

        # train history per account (warm profile + mask + picker counts)
        self.train_full = {u: set(g["nid"]) for u, g in
                           train_i.groupby("dummy_user_id")}
        # dev history (presets/demo parity with the MIND-era _d contract)
        dev_i = pd.read_parquet(_REPO / comp["interactions_dev_path"],
                                columns=["dummy_user_id", "nid"])
        self.dev_full = {u: set(g["nid"]) for u, g in
                         dev_i.groupby("dummy_user_id")}

    # -- interface data dict (what the web layer reads) ------------------

    @property
    def _d(self) -> dict:
        return {"era": "indo",
                "full_nids": self.full_nids,
                "nid_to_full": self.nid_to_full,
                "user_map": self._user_map,
                "item_map": self.item_map,
                "train_full": self.train_full,
                "dev_full": self.dev_full,
                "catalog_size": len(self.full_nids),
                "als_items": len(self._als_items)}

    # -- scores -----------------------------------------------------------

    def _cbf_scores(self, profile_rows: np.ndarray) -> np.ndarray:
        prof = self._tfidf[profile_rows].mean(axis=0)
        return np.asarray(self._tfidf @ prof.T).ravel()

    def _als_scores(self, user_idx: int | None,
                    session_nids: list[str] | None = None) -> np.ndarray:
        """Catalog-length ALS scores; factorless items pin to the -1.0 floor
        (the evaluated ranker semantics: never fake factors)."""
        n = len(self.full_nids)
        if user_idx is not None:
            dots = self._user_factors[user_idx] @ self._item_factors.T
            out = np.full(n, -1.0)
            out[np.array([self._nid_pos[n] for n in self._als_items])] = dots
            return out
        # cold session: mean factor of seen items that have factors
        rows = [self._item_row[n] for n in (session_nids or [])
                if n in self._item_row]
        if not rows:
            return np.full(n, -1.0)
        pu = self._item_factors[rows].mean(axis=0)
        dots = pu @ self._item_factors.T
        out = np.full(n, -1.0)
        out[np.array([self._nid_pos[n] for n in self._als_items])] = dots
        return out

    def _blend(self, cf_raw: np.ndarray, cbf_raw: np.ndarray) -> np.ndarray:
        """Exactly the evaluated hybrid: a*minmax(cf) + (1-a)*minmax(cbf)."""
        return self.alpha * minmax(cf_raw) + (1.0 - self.alpha) * minmax(cbf_raw)

    def _mask(self, scores: np.ndarray, nids: set[str]) -> None:
        for n in nids:
            p = self._nid_pos.get(n)
            if p is not None:
                scores[p] = -np.inf

    def _top(self, scores: np.ndarray, top_k: int) -> list[dict]:
        k = min(top_k, len(scores))
        idx = np.argsort(-np.nan_to_num(scores, neginf=-np.inf),
                         kind="stable")[:k]
        return [{"nid": self.full_nids[i], "title": self._titles[i],
                 "category": self._categories[i],
                 "subcategory": None, "score": float(scores[i])}
                for i in idx]

    # -- public API (mirrors HybridRecommender) ----------------------------

    def recommend_user(self, user_id: str, top_k: int = 10,
                       alpha: float | None = None) -> list:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if user_id not in self._user_map:
            raise UnknownUserError(
                f"user {user_id!r} has no ALS factor; use recommend_session")
        seen = self.train_full.get(user_id, set())
        rows = np.array(sorted(self._nid_pos[n] for n in seen
                               if n in self._nid_pos))
        cbf_raw = self._cbf_scores(rows)
        cf_raw = self._als_scores(user_idx=self._user_map[user_id])
        s = self._blend(cf_raw, cbf_raw)
        self._mask(s, seen)
        return self._top(s, top_k)

    def recommend_session(self, session_nids: list, top_k: int = 10,
                          alpha: float | None = None) -> list:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if not session_nids:
            raise ValueError("session_nids must be non-empty")
        known = [n for n in session_nids if n in self._nid_pos]
        if not known:
            raise ValueError("no session item found in catalog")
        cbf_raw = self._cbf_scores(
            np.array([self._nid_pos[n] for n in known]))
        cf_raw = self._als_scores(user_idx=None, session_nids=known)
        s = self._blend(cf_raw, cbf_raw)
        self._mask(s, set(known))
        return self._top(s, top_k)

    def similar(self, nid: str, top_k: int = 10) -> list:
        if nid not in self._nid_pos:
            raise KeyError(f"item {nid!r} not in catalog")
        i = self._nid_pos[nid]
        sims = np.asarray(self._tfidf[i].dot(self._tfidf.T).todense()).ravel()
        sims[i] = -np.inf
        return self._top(sims, top_k)

    def article(self, nid: str) -> dict:
        if nid not in self._nid_pos:
            raise KeyError(f"item {nid!r} not in catalog")
        i = self._nid_pos[nid]
        return {"nid": nid, "title": self._titles[i],
                "abstract": self._abstracts[i], "category": self._categories[i],
                "subcategory": None}


def load_indo_recommender(config_path: str = "configs/indo_serving.yaml"
                          ) -> IndoHybridRecommender:
    return IndoHybridRecommender(load_config(config_path))
