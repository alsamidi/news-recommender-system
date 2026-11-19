"""Evaluation harness for the Indo corpus (4 systems + sensitivity).

Ranking protocol (plan): full-catalog DEV ranking per account — every dev
item is a candidate, no sampled negatives; relevant set = the dev items that
account actually viewed. Metrics: NDCG@10, AP@10 (MAP), Recall@10.

Systems:
  popularity : TRAIN view counts desc, nid asc tie-break (feed pattern).
  cbf        : TF-IDF (fresh in src/phase2, fit on TRAIN catalog
               processed_text, transform over FULL catalog); account profile
               = mean of its TRAIN viewed-item vectors; cosine scores.
  als        : dot(user_factors, item_factors.T) on the ALS factors trained
               on TRAIN interactions. Dev items without factors score -inf
               (they cannot have factors — plan rule: never fake them).
  hybrid     : a * minmax(als) + (1-a) * minmax(cbf), min-max per account
               over the full dev candidate vector (MIND evaluator pattern);
               a in {0.2, 0.4, 0.6, 0.8} grid — winner reported, never
               hardcoded, never sent by the web layer.
"""
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

ALPHA_GRID = (0.2, 0.4, 0.6, 0.8)


# ---------------------------------------------------------------------------
# metrics (verified against hand-computed values in tests)
# ---------------------------------------------------------------------------

def dcg(rels, k):
    return float(sum(r / np.log2(i + 2) for i, r in enumerate(rels[:k])))


def ndcg_at_k(ranked_ids, relevant, k=10):
    rels = [1.0 if i in relevant else 0.0 for i in ranked_ids[:k]]
    ideal = [1.0] * min(len(relevant), k)
    denom = dcg(ideal, k)
    return dcg(rels, k) / denom if denom > 0 else 0.0


def ap_at_k(ranked_ids, relevant, k=10):
    hits, s = 0, 0.0
    for i, nid in enumerate(ranked_ids[:k]):
        if nid in relevant:
            hits += 1
            s += hits / (i + 1)
    return s / min(len(relevant), k) if relevant else 0.0


def recall_at_k(ranked_ids, relevant, k=10):
    if not relevant:
        return 0.0
    hit = sum(1 for nid in ranked_ids[:k] if nid in relevant)
    return hit / len(relevant)


def precision_at_k(ranked_ids, relevant, k=10):
    """Relevant fraction of the top-k list (0.0 for an empty prediction)."""
    if k <= 0 or not ranked_ids:
        return 0.0
    top = ranked_ids[:k]
    return sum(1 for nid in top if nid in relevant) / len(top)


def f1_at_k(ranked_ids, relevant, k=10):
    """Harmonic mean of Precision@k and Recall@k at the same cutoff.

    Zero when both are zero: the harmonic mean is undefined there, and every
    other metric scores a hitless ranking as 0.
    """
    p = precision_at_k(ranked_ids, relevant, k)
    r = recall_at_k(ranked_ids, relevant, k)
    if p + r == 0.0:
        return 0.0
    return 2.0 * p * r / (p + r)


def map_at_k(ranked_ids, relevant, k=10):
    """Same quantity as ``ap_at_k`` under the literature name (MAP@K)."""
    return ap_at_k(ranked_ids, relevant, k)


def evaluate_ranking(ranked_ids, relevant, k=10):
    ap = ap_at_k(ranked_ids, relevant, k)
    return {
        f"ndcg@{k}": ndcg_at_k(ranked_ids, relevant, k),
        f"ap@{k}": ap,
        f"map@{k}": ap,  # same quantity under the literature name
        f"precision@{k}": precision_at_k(ranked_ids, relevant, k),
        f"recall@{k}": recall_at_k(ranked_ids, relevant, k),
        f"f1@{k}": f1_at_k(ranked_ids, relevant, k),
        "n_relevant": len(relevant),
    }


# ---------------------------------------------------------------------------
# rankers
# ---------------------------------------------------------------------------

def popularity_ranker(train_events: pd.DataFrame, dev_items: list[str]):
    """TRAIN counts desc, nid asc tie-break; score = count (dev items only).

    Account-independent: returns a fixed score vector for every account.
    """
    counts = train_events["nid"].value_counts()
    dev = pd.DataFrame({"nid": dev_items})
    dev["count"] = dev["nid"].map(counts).fillna(0)
    dev = dev.sort_values(["count", "nid"], ascending=[False, True])
    order = {nid: i for i, nid in enumerate(dev["nid"])}
    scores = np.array([-order[n] for n in dev_items], dtype=float)

    def score(_account):
        return scores

    return score


def build_tfidf(catalog_train: pd.DataFrame, catalog_full: pd.DataFrame):
    """Fit TF-IDF on TRAIN processed_text only; transform the full catalog."""
    vec = TfidfVectorizer()
    vec.fit(catalog_train["processed_text"].fillna("").tolist())
    mat = vec.transform(catalog_full["processed_text"].fillna("").tolist())
    return vec, mat


def cbf_ranker(tfidf_mat, row_of: dict, train_events: pd.DataFrame,
               dev_items: list[str]):
    """Cosine(account profile mean-vector, dev item vectors)."""
    import sklearn.preprocessing as pp
    tfidf_mat = pp.normalize(tfidf_mat)
    # profile: mean of viewed-item vectors per account
    train_events = train_events.copy()
    train_events["row"] = train_events["nid"].map(row_of)
    profiles = {}
    grouped = train_events.groupby("dummy_user_id")["row"]
    for account, rows in grouped:
        idx = rows.dropna().astype(int).to_numpy()
        profiles[account] = np.asarray(tfidf_mat[idx].mean(axis=0))
    dev_rows = np.array([row_of[n] for n in dev_items])
    dev_mat = tfidf_mat[dev_rows]

    def score(account):
        p = profiles.get(account)
        if p is None:
            return np.zeros(len(dev_items))
        sims = dev_mat @ p.T
        return np.asarray(sims).ravel()

    return score


def als_ranker(model, uidx: dict, iidx: dict, dev_items: list[str]):
    """Dot-product scores over items WITH factors.

    Dev items without factors are unrankable for ALS — they get -1.0 (a
    floor below every real dot-product here) instead of -inf so hybrid
    min-max blending stays finite; they only surface when nothing better
    exists.
    """
    u_f, i_f = model.user_factors, model.item_factors
    dev_rows = np.array([iidx.get(n, -1) for n in dev_items])

    def score(account):
        u = uidx.get(account)
        if u is None:
            return np.full(len(dev_items), -1.0)
        out = np.full(len(dev_items), -1.0)
        known = np.flatnonzero(dev_rows >= 0)
        if len(known):
            out[known] = i_f[dev_rows[known]] @ u_f[u]
        return out

    return score


def minmax(v):
    """Min-max to [0,1]; inf-safe (non-finite entries pin to 0 after)."""
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


# ---------------------------------------------------------------------------
# pipeline driver
# ---------------------------------------------------------------------------

def rank_topk(score_fn, dev_items, accounts, k=10):
    """Top-k per account from a FULL-catalog scoring (no sampled negatives).

    dev_items must be sorted ascending (they are, from evaluate_point): the
    stable argsort on -score then breaks ties by nid ascending. Metrics are
    all @10, so only the top-k slice is materialized; every dev item is
    still scored by the system.
    """
    item_arr = np.array(dev_items)
    out = {}
    for a in accounts:
        s = np.asarray(score_fn(a), dtype=float)
        s = np.nan_to_num(s, nan=-np.inf, neginf=-np.inf, posinf=1e18)
        order = np.argsort(-s, kind="stable")[:k]
        out[a] = item_arr[order].tolist()
    return out


def evaluate_point(catalog_full, catalog_train, train_events, dev_events,
                   als_model=None, uidx=None, iidx=None, alphas=ALPHA_GRID,
                   k=10):
    """One sensitivity point: all systems + hybrid grid on the dev split."""
    relevant = dev_events.groupby("dummy_user_id")["nid"].apply(set).to_dict()
    dev_items = sorted(catalog_full["nid"].unique())
    accounts = sorted(set(dev_events["dummy_user_id"]))

    vec, mat = build_tfidf(catalog_train, catalog_full)
    row_of = {n: i for i, n in enumerate(catalog_full["nid"])}

    rankers = {
        "popularity": rank_topk(
            popularity_ranker(train_events, dev_items), dev_items, accounts,
            k),
    }
    cbf_fn = cbf_ranker(mat, row_of, train_events, dev_items)
    rankers["cbf"] = rank_topk(cbf_fn, dev_items, accounts, k)
    if als_model is not None:
        als_fn = als_ranker(als_model, uidx, iidx, dev_items)
        rankers["als"] = rank_topk(als_fn, dev_items, accounts, k)
        # hybrid inputs: normalize ONCE per account, blend per alpha
        accounts_arr = accounts
        als_m = {a: minmax(als_fn(a)) for a in accounts_arr}
        cbf_m = {a: minmax(cbf_fn(a)) for a in accounts_arr}
        for alpha in alphas:
            def hyb(a, alpha=alpha):
                return alpha * als_m[a] + (1 - alpha) * cbf_m[a]
            rankers[f"hybrid_a{alpha}"] = rank_topk(hyb, dev_items, accounts,
                                                    k)

    metric_keys = [key for key in
                   evaluate_ranking([], set(), k) if key != "n_relevant"]
    report = {}
    for name, ranking in rankers.items():
        per = [evaluate_ranking(ranking[a], relevant.get(a, set()), k)
               for a in accounts]
        row = {f"{key}_mean": float(np.mean([p[key] for p in per]))
               for key in metric_keys}
        row["n_accounts"] = len(accounts)
        report[name] = row
    return report
