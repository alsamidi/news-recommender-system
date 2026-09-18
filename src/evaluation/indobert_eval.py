"""Eksperimen 2: IndoBERT standalone + sweep alpha 0.0->1.0 + slice seen/unseen.

Protokol IDENTIK dengan TF-IDF (src/evaluation/eval_standalone.py + alpha_sweep.py):
- ruang item ALS (3394), test dev via train maps, mask train
- 1652 user eval yang sama, K=5/10/20, rumus P/R/MAP/NDCG sama
- profil user = mean embedding item train (tanpa renormalisasi, sama spt TF-IDF)
- minmax per user sebelum weighted sum (sama spt evaluate_hybrid)

Output: models/indobert_eval.json
"""
import json
import pickle
import sys

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

sys.path.insert(0, "src")

K_VALUES = [5, 10, 20]
ALPHAS = [round(a * 0.1, 1) for a in range(0, 11)]


def minmax(x):
    lo, hi = x.min(), x.max()
    return np.zeros_like(x) if hi <= lo else (x - lo) / (hi - lo)


def main():
    with open("models/als_model.pkl", "rb") as f:
        als = pickle.load(f)
    user_map, item_map = als["user_map"], als["item_map"]
    train_matrix = als["train_matrix"].tocsr()
    uf = np.load("models/als_user_factors.npy")
    itf = np.load("models/als_item_factors.npy")

    news = pd.read_parquet("data/processed/news_processed.parquet").reset_index(drop=True)
    emb_full = np.load("models/indobert_embeddings.npy")
    assert emb_full.shape[0] == len(news), (emb_full.shape, len(news))
    row_of = {nid: i for i, nid in enumerate(news["nid"].tolist())}
    inv_item = [None] * len(item_map)
    for nid, idx in item_map.items():
        inv_item[idx] = nid
    items = emb_full[[row_of[n] for n in inv_item]].astype(np.float64)  # (3394, dim)
    print(f"indobert items: {items.shape}", flush=True)

    tr_full = pd.read_parquet("data/processed/interactions_train.parquet")
    seen_int = set(tr_full["nid"].unique())  # untuk slice seen/unseen
    df = pd.read_parquet("data/processed/interactions_dev.parquet")
    df = df[df["user_id"].isin(user_map) & df["nid"].isin(item_map)]
    test_matrix = csr_matrix(
        (df["weight"].values,
         (df.user_id.map(user_map).values, df.nid.map(item_map).values)),
        shape=train_matrix.shape).tocsr()

    n_users, n_items = test_matrix.shape
    sampled = [u for u in range(n_users) if test_matrix[u].nnz > 0][:2000]
    eval_users = []
    for u in sampled:
        ti = set(train_matrix[u].indices)
        if not ti:
            continue
        if (set(test_matrix[u].indices) - ti):
            eval_users.append(u)
    print(f"eval users: {len(eval_users)}", flush=True)
    inv_nid = {idx: nid for nid, idx in item_map.items()}

    # skor precompute: content per user + cf semua
    content_all = np.zeros((len(eval_users), n_items))
    for i, u in enumerate(eval_users):
        prof = items[list(train_matrix[u].indices)].mean(axis=0)
        content_all[i] = minmax(np.asarray(prof @ items.T).ravel())
    cf_all = minmax(uf @ itf.T)  # minmax global spt pola hybrid? TIDAK -> per user di loop

    cf_raw = uf @ itf.T
    rows_out = []
    for alpha in ALPHAS:
        res = {f"{m}@{k}": [] for m in ["precision", "recall", "map", "ndcg"] for k in K_VALUES}
        for i, u in enumerate(eval_users):
            ti = set(train_matrix[u].indices)
            rel = set(test_matrix[u].indices) - ti
            s = alpha * content_all[i] + (1 - alpha) * minmax(cf_raw[u])
            s[list(ti)] = -np.inf
            kmax = max(K_VALUES)
            top = np.argpartition(-s, kmax)[:kmax]
            top = top[np.argsort(-s[top])]
            rec = top.tolist()
            for k in K_VALUES:
                rk = rec[:k]
                hits = sum(1 for r in rk if r in rel)
                prec = hits / k if k else 0
                rec_ = hits / len(rel) if rel else 0
                ap, hc = 0, 0
                for j, r in enumerate(rk):
                    if r in rel:
                        hc += 1
                        ap += hc / (j + 1)
                ap = ap / min(len(rel), k) if rel else 0

                def dcg(rels):
                    return sum(r / np.log2(j + 2) for j, r in enumerate(rels))
                ideal = sorted([1] * len(rel) + [0] * (k - len(rel)), reverse=True)
                act = [1 if r in rel else 0 for r in rk]
                ndcg = dcg(act) / dcg(ideal) if dcg(ideal) > 0 else 0
                res[f"precision@{k}"].append(prec)
                res[f"recall@{k}"].append(rec_)
                res[f"map@{k}"].append(ap)
                res[f"ndcg@{k}"].append(ndcg)
        rows_out.append({"alpha": alpha, **{m: float(np.mean(v)) for m, v in res.items()}})
        r = rows_out[-1]
        print(f"alpha={alpha:.1f} ndcg@10={r['ndcg@10']:.5f} map@10={r['map@10']:.5f}", flush=True)

    # slice seen/unseen + coverage pada alpha=1.0 (pure IndoBERT) vs TF-IDF tersimpan
    cov_items, user_hit, seen_hit, unseen_hit = set(), 0, 0, 0
    seen_rel_total = unseen_rel_total = 0
    for i, u in enumerate(eval_users):
        ti = set(train_matrix[u].indices)
        rel = set(test_matrix[u].indices) - ti
        s = content_all[i].copy()
        s[list(ti)] = -np.inf
        top = np.argpartition(-s, 10)[:10]
        top = set(top[np.argsort(-s[top])].tolist())
        cov_items |= top
        if top & rel:
            user_hit += 1
        for r in rel:
            if inv_nid[r] in seen_int:
                seen_rel_total += 1
                if r in top:
                    seen_hit += 1
            else:
                unseen_rel_total += 1
                if r in top:
                    unseen_hit += 1
    slice10 = {
        "distinct_items_cov10": len(cov_items),
        "catalog_coverage@10": float(len(cov_items) / n_items),
        "users_with_ge1_hit@10": int(user_hit),
        "pct_users_hit@10": float(user_hit / len(eval_users)),
        "seen_relevant_total": int(seen_rel_total),
        "seen_relevant_hit@10": int(seen_hit),
        "seen_hit_rate@10": float(seen_hit / seen_rel_total) if seen_rel_total else 0.0,
        "unseen_relevant_total": int(unseen_rel_total),
        "unseen_relevant_hit@10": int(unseen_hit),
        "unseen_hit_rate@10": float(unseen_hit / unseen_rel_total) if unseen_rel_total else 0.0,
    }

    out = {"protocol": "identik TF-IDF: als-item-space, mask-train, user eval sama, K=5/10/20",
           "model": "firqaaa/indo-sentence-bert-base", "n_eval_users": len(eval_users),
           "alpha_sweep": rows_out, "pure_indobert_slice@10": slice10}
    with open("models/indobert_eval.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nalpha | ndcg@10 | map@10")
    for r in rows_out:
        print(f"{r['alpha']:4.1f} | {r['ndcg@10']:.5f} | {r['map@10']:.5f}")
    print(json.dumps(slice10, indent=2))


if __name__ == "__main__":
    main()
