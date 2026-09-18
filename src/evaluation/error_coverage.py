"""Analisis error/coverage: mengapa Content menang atas CF.
Level 1 (full): seluruh train/dev interactions + katalog news.
Level 2 (eval): subruang ALS yang dipakai metrik (drop unseen user/item).
Coverage: CF (alpha=0) vs Content (alpha=1) vs Hybrid (alpha=0.8), K=10.
"""
import json
import pickle
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

K = 10
ALPHA_HYB = 0.8

tr = pd.read_parquet("data/processed/interactions_train.parquet")
dv = pd.read_parquet("data/processed/interactions_dev.parquet")
nw = pd.read_parquet("data/processed/news_processed.parquet")
with open("models/als_model.pkl", "rb") as f:
    als = pickle.load(f)
user_map, item_map = als["user_map"], als["item_map"]
train_matrix = als["train_matrix"].tocsr()
with open("models/tfidf_baseline.pkl", "rb") as f:
    tfidf_art = pickle.load(f)
tfidf_train = tfidf_art["train_matrix"].tocsr()
uf = np.load("models/als_user_factors.npy")
itf = np.load("models/als_item_factors.npy")

out = {}

# ---------- LEVEL 1: full ----------
train_users = set(tr.user_id.unique())
dev_users = set(dv.user_id.unique())
train_items_int = set(tr.nid.unique())          # item pernah diklik di train
dev_items_rel = set(dv.nid.unique())            # relevant items di dev
train_news = set(nw[nw.split == "train"].nid)
dev_news = set(nw[nw.split == "dev"].nid)

unseen_int = dev_items_rel - train_items_int
unseen_news = dev_news - train_news
out["full"] = {
    "train_rows": int(len(tr)), "dev_rows": int(len(dv)),
    "train_users": len(train_users), "dev_users": len(dev_users),
    "dev_users_with_train_history": int(len(dev_users & train_users)),
    "dev_users_without_train_history": int(len(dev_users - train_users)),
    "pct_dev_users_without_train_history": float(len(dev_users - train_users) / len(dev_users)),
    "train_distinct_click_items": len(train_items_int),
    "dev_distinct_relevant_items": len(dev_items_rel),
    "dev_relevant_items_unseen_in_train_interactions": int(len(unseen_int)),
    "pct_dev_relevant_items_unseen_in_train_interactions": float(len(unseen_int) / len(dev_items_rel)),
    "dev_rows_item_unseen_in_train": float((~dv.nid.isin(train_items_int)).mean()),
    "dev_news_count": len(dev_news), "train_news_count": len(train_news),
    "dev_news_unseen_in_train_catalog": int(len(unseen_news)),
    "pct_dev_news_unseen_in_train_catalog": float(len(unseen_news) / len(dev_news)),
    "dev_rows_per_user_mean": float(dv.groupby("user_id").size().mean()),
    "dev_rows_per_user_median": float(dv.groupby("user_id").size().median()),
}
# distribusi relevant per user (dev full)
dpu = dv.groupby("user_id").size()
out["full"]["relevant_per_user_p25_p50_p75_p90"] = [float(dpu.quantile(q)) for q in [0.25, 0.5, 0.75, 0.9]]

# ---------- CF vs Content candidate reach (full) ----------
als_items = set(item_map.keys())
cf_reachable = dev_items_rel & als_items
out["candidate_reach"] = {
    "als_item_space": len(als_items),
    "dev_relevant_in_cf_space": int(len(cf_reachable)),
    "pct_dev_relevant_in_cf_space": float(len(cf_reachable) / len(dev_items_rel)),
    "pct_dev_relevant_only_content": float((len(dev_items_rel) - len(cf_reachable)) / len(dev_items_rel)),
    "dev_rows_in_cf_space": float(dv.nid.isin(als_items).mean()),
    "dev_rows_user_in_cf_space": float(dv.user_id.isin(user_map).mean()),
    "dev_rows_both_in_cf_space": float((dv.user_id.isin(user_map) & dv.nid.isin(als_items)).mean()),
    "content_reach_note": "content TF-IDF bisa merepresentasikan SEMUA news berteks (train+dev catalog), CF hanya 3394 item ALS",
}

# ---------- LEVEL 2: eval subspace ----------
df = dv[dv.user_id.isin(user_map) & dv.nid.isin(item_map)]
test_matrix = csr_matrix(
    (df["weight"].values,
     (df.user_id.map(user_map).values, df.nid.map(item_map).values)),
    shape=train_matrix.shape).tocsr()
n_users, n_items = test_matrix.shape
sampled = [u for u in range(n_users) if test_matrix[u].nnz > 0][:2000]
eval_users, rel_counts = [], []
for u in sampled:
    ti = set(train_matrix[u].indices)
    if not ti:
        continue
    rel = set(test_matrix[u].indices) - ti
    if not rel:
        continue
    eval_users.append(u)
    rel_counts.append(len(rel))
rel_counts = np.array(rel_counts)
out["eval"] = {
    "n_users_train_space": int(n_users), "n_items_cf_space": int(n_items),
    "sampled_test_users": len(sampled), "n_eval_users": len(eval_users),
    "relevant_per_eval_user_mean": float(rel_counts.mean()),
    "relevant_per_eval_user_median": float(np.median(rel_counts)),
    "relevant_per_eval_user_p90": float(np.quantile(rel_counts, 0.9)),
    "relevant_per_eval_user_eq1": float((rel_counts == 1).mean()),
}

# ---------- coverage CF vs Content vs Hybrid ----------
train_nids = nw[nw.split == "train"].nid.tolist()
row_of = {nid: i for i, nid in enumerate(train_nids)}
inv_item = [None] * len(item_map)
for nid, idx in item_map.items():
    inv_item[idx] = nid
tfidf_items = tfidf_train[[row_of[n] for n in inv_item]].tocsr()


def minmax(x):
    lo, hi = x.min(), x.max()
    return np.zeros_like(x) if hi <= lo else (x - lo) / (hi - lo)


def content_scores(u):
    ti = list(train_matrix[u].indices)
    prof = tfidf_items[ti].mean(axis=0)
    return minmax(np.asarray(prof @ tfidf_items.T).ravel())


cf_all = uf @ itf.T
recs = {"cf": set(), "content": set(), "hybrid": set()}
hits = {"cf": 0, "content": 0, "hybrid": 0}   # user dengan >=1 hit @10
hit_items = {"cf": set(), "content": set(), "hybrid": set()}  # distinct relevant items pernah kena hit
union_rel = set()
cf_only_hit = content_only_hit = both_hit = neither = 0
for u in eval_users:
    ti = list(set(train_matrix[u].indices))
    rel = set(test_matrix[u].indices) - set(ti)
    union_rel |= rel
    cs = content_scores(u)
    fs = minmax(cf_all[u])
    hs = ALPHA_HYB * cs + (1 - ALPHA_HYB) * fs
    tops = {}
    for name, s in (("cf", fs.copy()), ("content", cs.copy()), ("hybrid", hs.copy())):
        s[ti] = -np.inf
        top = np.argpartition(-s, K)[:K]
        top = top[np.argsort(-s[top])]
        tops[name] = set(top.tolist())
        recs[name] |= tops[name]
        if tops[name] & rel:
            hits[name] += 1
            hit_items[name] |= (tops[name] & rel)
    c_hit = bool(tops["content"] & rel)
    f_hit = bool(tops["cf"] & rel)
    if c_hit and not f_hit:
        content_only_hit += 1
    elif f_hit and not c_hit:
        cf_only_hit += 1
    elif f_hit and c_hit:
        both_hit += 1
    else:
        neither += 1

n_eval = len(eval_users)
out["coverage_at_10"] = {
    m: {"distinct_items": len(s), "catalog_coverage": float(len(s) / n_items)}
    for m, s in recs.items()
}
out["coverage_at_10"]["only_content_items"] = len(recs["content"] - recs["cf"] - recs["hybrid"])
out["coverage_at_10"]["overlap_all_three"] = len(recs["content"] & recs["cf"] & recs["hybrid"])
out["user_hit_at_10"] = {m: {"users_with_ge1_hit": int(v), "pct": float(v / n_eval)} for m, v in hits.items()}
out["relevant_item_hit_coverage"] = {
    m: {"distinct_relevant_items_hit": len(s), "pct_of_union_relevant": float(len(s) / len(union_rel))}
    for m, s in hit_items.items()
}
out["user_hit_split_content_vs_cf"] = {
    "content_only": int(content_only_hit), "cf_only": int(cf_only_hit),
    "both": int(both_hit), "neither": int(neither),
    "pct_content_only": float(content_only_hit / n_eval),
    "pct_cf_only": float(cf_only_hit / n_eval),
    "pct_both": float(both_hit / n_eval),
    "pct_neither": float(neither / n_eval),
}
out["union_relevant_eval"] = len(union_rel)

with open("models/error_coverage.json", "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
