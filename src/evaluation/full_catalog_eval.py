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


def expand_cf_scores(cf_norm_known: np.ndarray, als_full_pos: np.ndarray,
                     n_full: int, alpha: float) -> np.ndarray:
    """Expand ALS-space CF scores to full-catalog length.

    Known slots get their min-maxed CF value; unknown slots get 0.0 so the
    hybrid can still rank them via content. At exactly alpha == 0.0 (pure
    CF) unknown slots are -inf so CF recommends only ALS-known items.
    """
    full = np.zeros(n_full, dtype=float)
    full[np.asarray(als_full_pos)] = np.asarray(cf_norm_known, dtype=float)
    if alpha == 0.0:
        mask = np.ones(n_full, dtype=bool)
        mask[np.asarray(als_full_pos)] = False
        full[mask] = -np.inf
    return full


def seeded_sample(users: list, max_users: int, seed: int = 42) -> list:
    """Deterministic sample: shuffle a copy with seed, take first max_users."""
    rng = np.random.default_rng(seed)
    order = list(users)
    rng.shuffle(order)
    return order[:max_users]


def load_all():
    """Load frozen artifacts; build full-catalog TF-IDF (transform-only).

    Scores are stored float32 (plan risk note: 2GB free RAM; float64 for
    2000 users x 93698 items would exhaust memory, ranking unchanged).
    """
    import pickle
    import pandas as pd

    news = pd.read_parquet("data/processed/news_processed.parquet").reset_index(drop=True)
    assert len(news) == 93698, f"catalog rows {len(news)} != 93698"
    full_nids = news["nid"].tolist()
    nid_to_full = {n: i for i, n in enumerate(full_nids)}
    full_texts = news["processed_text"].fillna("").tolist()
    assert all(isinstance(t, str) for t in full_texts)

    with open("models/tfidf_baseline.pkl", "rb") as f:
        tfidf_art = pickle.load(f)
    vectorizer = tfidf_art["vectorizer"]
    train_matrix = tfidf_art["train_matrix"].tocsr()
    n_train_news = int((news["split"] == "train").sum())
    assert train_matrix.shape[0] == n_train_news == 51282, (
        train_matrix.shape, n_train_news)
    vocab_size = len(vectorizer.vocabulary_)

    # TRANSFORM ONLY — the vectorizer is frozen (fit on train). Never fit here.
    full_tfidf = vectorizer.transform(full_texts).tocsr()
    assert full_tfidf.shape == (93698, train_matrix.shape[1]), full_tfidf.shape
    assert len(vectorizer.vocabulary_) == vocab_size, "vocabulary changed: LEAKAGE"

    with open("models/als_model.pkl", "rb") as f:
        als = pickle.load(f)
    user_map, item_map = als["user_map"], als["item_map"]
    als_train = als["train_matrix"].tocsr()
    user_factors = np.load("models/als_user_factors.npy").astype(np.float32)
    item_factors = np.load("models/als_item_factors.npy").astype(np.float32)
    assert user_factors.shape[0] == len(user_map) and item_factors.shape[0] == len(item_map)

    inv_item = [None] * len(item_map)
    for nid, idx in item_map.items():
        inv_item[idx] = nid
    assert all(n in nid_to_full for n in inv_item), "ALS nid missing from catalog"
    als_full_pos = np.array([nid_to_full[n] for n in inv_item])
    assert len(item_map) == 3394, f"ALS items {len(item_map)} != 3394"

    tr = pd.read_parquet("data/processed/interactions_train.parquet")
    dv = pd.read_parquet("data/processed/interactions_dev.parquet")

    # Full train-clicked full-indices per warm user (ALL train nids, incl. out-of-ALS).
    tr = tr[tr["user_id"].isin(user_map)]
    missing_tr = set(tr["nid"].unique()) - set(nid_to_full)
    assert not missing_tr, f"{len(missing_tr)} train nids lack catalog text"
    tr["full_idx"] = tr["nid"].map(nid_to_full)
    train_full = tr.groupby("user_id")["full_idx"].apply(set).to_dict()

    # Full dev-relevant full-indices per warm user (KEEP out-of-ALS items).
    dv = dv[dv["user_id"].isin(user_map)]
    missing_dv = set(dv["nid"].unique()) - set(nid_to_full)
    assert not missing_dv, f"{len(missing_dv)} dev nids lack catalog text"
    dv["full_idx"] = dv["nid"].map(nid_to_full)
    dev_full = dv.groupby("user_id")["full_idx"].apply(set).to_dict()

    return {
        "news": news, "full_nids": full_nids, "nid_to_full": nid_to_full,
        "full_tfidf": full_tfidf, "vocab_size": vocab_size,
        "user_map": user_map, "item_map": item_map, "inv_item": inv_item,
        "als_full_pos": als_full_pos, "als_train": als_train,
        "user_factors": user_factors, "item_factors": item_factors,
        "train_full": train_full, "dev_full": dev_full,
    }


def precompute_user_scores(eval_users: list, data: dict):
    """Return dict user_id -> (content_norm_full32, cf_norm_known32).

    content profile = mean TF-IDF rows of the user's FULL train set
    (dot = cosine since rows are L2-normalized); min-maxed per user.
    cf = user factor dot item factors; min-maxed per user over ALS space.
    float32: 2000 users x 93698 items = ~750MB (float64 would be ~1.5GB).
    Ranking unaffected (monotone cast, top-k identical).
    """
    full_tfidf = data["full_tfidf"]
    uf, itf = data["user_factors"], data["item_factors"]
    user_map = data["user_map"]
    train_full = data["train_full"]
    out = {}
    for uid in eval_users:
        ti = sorted(train_full[uid])
        prof = full_tfidf[ti].mean(axis=0)
        content_raw = np.asarray(prof @ full_tfidf.T).ravel()
        u_idx = user_map[uid]
        cf_raw = uf[u_idx] @ itf.T
        out[uid] = (_minmax(content_raw).astype(np.float32),
                    _minmax(cf_raw).astype(np.float32))
    return out


def sweep_table_b(eval_users: list, data: dict, scores: dict,
                  k_values=(5, 10, 20), alphas=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)):
    """Full-catalog sweep. Returns list of row dicts (one per alpha)."""
    n_full = len(data["full_nids"])
    als_pos = data["als_full_pos"]
    train_full, dev_full = data["train_full"], data["dev_full"]
    kmax = max(k_values)
    rows = []
    for alpha in alphas:
        acc = {f"{m}@{k}": [] for m in ("precision", "recall", "map", "ndcg") for k in k_values}
        rec_union, hit_users, n_eval = set(), 0, 0
        for uid in eval_users:
            ti = train_full[uid]
            rel = dev_full[uid] - ti
            if not rel:
                continue
            n_eval += 1
            c_norm, cf_norm = scores[uid]
            cf_full = expand_cf_scores(cf_norm, als_pos, n_full, alpha)
            s = alpha * c_norm + (1 - alpha) * cf_full
            s[list(ti)] = -np.inf
            rec = _topk_sorted(s, kmax)
            if kmax >= 10:
                rec_union.update(rec[:10])
                if set(rec[:10]) & rel:
                    hit_users += 1
            acc_row = _metrics_at_ks(rec, rel, list(k_values))
            for k_, v_ in acc_row.items():
                acc[k_].append(v_)
        row = {"alpha": alpha, "n_eval": n_eval,
               "coverage@10": len(rec_union) / n_full,
               "distinct_items@10": len(rec_union),
               "hit_rate@10": (hit_users / n_eval) if n_eval else 0.0}
        for m_, vs_ in acc.items():
            row[m_] = float(np.mean(vs_)) if vs_ else 0.0
        rows.append(row)
    return rows


def main():
    raise NotImplementedError


if __name__ == "__main__":
    main()
