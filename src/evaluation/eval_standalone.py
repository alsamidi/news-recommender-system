"""Evaluasi standalone Content-Based (TF-IDF) + Popularity.
Protokol SAMA PERSIS dengan evaluate_hybrid di src/models/hybrid/train.py:
- ruang item = ALS (3394 item), TF-IDF di-align via nid
- test matrix dari interactions_dev via user_map/item_map train
- sampled = user ber-test-interaksi s.d. 2000 pertama (urutan indeks),
  skip user tanpa train_items / tanpa relevant (test - train)
- mask item train (-inf), top-K 5/10/20
- metrik P/R/MAP/NDCG dengan rumus identik
"""
import json
import pickle
import numpy as np
import pandas as pd
from scipy.sparse import load_npz


def _minmax(x):
    lo, hi = x.min(), x.max()
    if hi <= lo:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def _metrics_loop(score_fn, train_matrix, test_matrix, k_values, max_users=2000):
    n_users, _ = test_matrix.shape
    results = {f"{m}@{k}": [] for m in ["precision", "recall", "map", "ndcg"] for k in k_values}
    n_eval = 0
    sampled = [u for u in range(n_users) if test_matrix[u].nnz > 0][:max_users]
    for u_idx in sampled:
        train_items = set(train_matrix[u_idx].indices)
        if not train_items:
            continue
        relevant = set(test_matrix[u_idx].indices) - train_items
        if not relevant:
            continue
        n_eval += 1
        scores = score_fn(u_idx, train_items).astype(float)
        scores[list(train_items)] = -np.inf
        kmax = max(k_values)
        top = np.argpartition(-scores, kmax)[:kmax]
        top = top[np.argsort(-scores[top])]
        recommended = top.tolist()
        for k in k_values:
            rec_k = recommended[:k]
            hits = sum(1 for r in rec_k if r in relevant)
            prec = hits / k if k > 0 else 0
            rec = hits / len(relevant) if relevant else 0
            ap, hc = 0, 0
            for i, r in enumerate(rec_k):
                if r in relevant:
                    hc += 1
                    ap += hc / (i + 1)
            ap = ap / min(len(relevant), k) if relevant else 0

            def dcg(rels):
                return sum(r / np.log2(i + 2) for i, r in enumerate(rels))
            ideal = sorted([1] * len(relevant) + [0] * (k - len(relevant)), reverse=True)
            actual = [1 if r in relevant else 0 for r in rec_k]
            ndcg = dcg(actual) / dcg(ideal) if dcg(ideal) > 0 else 0
            results[f"precision@{k}"].append(prec)
            results[f"recall@{k}"].append(rec)
            results[f"map@{k}"].append(ap)
            results[f"ndcg@{k}"].append(ndcg)
    final = {m: float(np.mean(v)) if v else 0.0 for m, v in results.items()}
    return final, n_eval, len(sampled)


def main():
    with open("models/tfidf_baseline.pkl", "rb") as f:
        tfidf_art = pickle.load(f)
    tfidf_train = tfidf_art["train_matrix"].tocsr()
    with open("models/als_model.pkl", "rb") as f:
        als_art = pickle.load(f)
    user_map, item_map = als_art["user_map"], als_art["item_map"]
    train_matrix = als_art["train_matrix"].tocsr()

    # align TF-IDF ke ruang item ALS via nid
    news = pd.read_parquet("data/processed/news_processed.parquet")
    train_nids = news[news["split"] == "train"]["nid"].tolist()
    row_of = {nid: i for i, nid in enumerate(train_nids)}
    inv_item = [None] * len(item_map)
    for nid, idx in item_map.items():
        inv_item[idx] = nid
    tfidf_items = tfidf_train[[row_of[n] for n in inv_item]].tocsr()

    # test matrix (sama spt hybrid: drop unseen)
    df = pd.read_parquet("data/processed/interactions_dev.parquet")
    df = df[df["user_id"].isin(user_map) & df["nid"].isin(item_map)]
    from scipy.sparse import csr_matrix
    test_matrix = csr_matrix(
        (df["weight"].values,
         (df["user_id"].map(user_map).values, df["nid"].map(item_map).values)),
        shape=train_matrix.shape).tocsr()

    k_values = [5, 10, 20]

    def content_scores(u_idx, train_items):
        profile = tfidf_items[list(train_items)].mean(axis=0)
        s = np.asarray(profile @ tfidf_items.T).ravel()
        return _minmax(s)

    pop = np.asarray(train_matrix.sum(axis=0)).ravel().astype(float)

    def pop_scores(u_idx, train_items):
        return pop.copy()

    cb, n_cb, n_samp = _metrics_loop(content_scores, train_matrix, test_matrix, k_values)
    pb, n_pb, _ = _metrics_loop(pop_scores, train_matrix, test_matrix, k_values)

    out = {
        "protocol": "same-as-hybrid: als-item-space, dev-via-train-maps, mask-train, first-2000-test-users, skip-empty-train/relevant",
        "k_values": k_values,
        "n_users_train_space": int(train_matrix.shape[0]),
        "n_sampled_test_users": int(n_samp),
        "n_eval_content": int(n_cb),
        "n_eval_popularity": int(n_pb),
        "content_based_tfidf": cb,
        "popularity_train_count": pb,
    }
    with open("models/standalone_baselines.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
