"""Alpha sweep lengkap 0.0 -> 1.0 memakai evaluate_hybrid yang sama persis."""
import json
import pickle
import pandas as pd
import sys
sys.path.insert(0, "src")
from models.hybrid.train import load_tfidf_artifacts, load_als_artifacts, build_test_interactions, evaluate_hybrid

CC = {"content_model_path": "models/tfidf_baseline.pkl",
      "content_embeddings_path": "models/tfidf_embeddings.npz",
      "cf_model_path": "models/als_model.pkl",
      "cf_user_factors_path": "models/als_user_factors.npy",
      "cf_item_factors_path": "models/als_item_factors.npy"}

_, tfidf_train_matrix, _ = load_tfidf_artifacts(CC["content_model_path"], CC["content_embeddings_path"])
model, user_map, item_map, als_train, uf, itf = load_als_artifacts(
    CC["cf_model_path"], CC["cf_user_factors_path"], CC["cf_item_factors_path"])

news = pd.read_parquet("data/processed/news_processed.parquet")
train_nids = news[news["split"] == "train"]["nid"].tolist()
row_of = {nid: i for i, nid in enumerate(train_nids)}
inv_item = [None] * len(item_map)
for nid, idx in item_map.items():
    inv_item[idx] = nid
tfidf_items = tfidf_train_matrix[[row_of[n] for n in inv_item]].tocsr()
test_matrix = build_test_interactions("data/processed/interactions_dev.parquet", user_map, item_map)

k_values = [5, 10, 20]
alphas = [round(a * 0.1, 1) for a in range(0, 11)]
rows = []
for alpha in alphas:
    print(f"alpha={alpha:.1f} ...", flush=True)
    r = evaluate_hybrid(tfidf_items, uf, itf, als_train, test_matrix, alpha, k_values)
    rows.append({"alpha": alpha, **r})
    print(f"  ndcg@10={r['ndcg@10']:.5f} map@10={r['map@10']:.5f}", flush=True)

with open("models/alpha_sweep.json", "w") as f:
    json.dump({"k_values": k_values, "rows": rows}, f, indent=2)

print("\nalpha | ndcg@10 | map@10 | prec@10 | rec@10")
for r in rows:
    print(f"{r['alpha']:4.1f} | {r['ndcg@10']:.5f} | {r['map@10']:.5f} | {r['precision@10']:.5f} | {r['recall@10']:.5f}")
