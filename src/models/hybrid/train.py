"""
Weighted Hybrid Model Training
Combines TF-IDF content similarity + ALS collaborative filtering via weighted sum
No LightFM dependency - works with Python 3.12
"""
import argparse
import json
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_tfidf_artifacts(content_model_path: str, embeddings_path: str):
    """Load TF-IDF vectorizer and item embeddings"""
    with open(content_model_path, "rb") as f:
        content_artifact = pickle.load(f)
    vectorizer = content_artifact["vectorizer"]
    train_matrix = content_artifact["train_matrix"]
    if embeddings_path.endswith(".npz"):
        from scipy.sparse import load_npz
        item_embeddings = load_npz(embeddings_path)  # sparse (n_items, n_features)
    else:
        item_embeddings = np.load(embeddings_path)  # shape: (n_items, n_features)
    return vectorizer, train_matrix, item_embeddings


def load_als_artifacts(cf_model_path: str, user_factors_path: str, item_factors_path: str):
    """Load ALS model and factors"""
    with open(cf_model_path, "rb") as f:
        cf_artifact = pickle.load(f)
    model = cf_artifact["model"]
    user_map = cf_artifact["user_map"]
    item_map = cf_artifact["item_map"]
    train_matrix = cf_artifact["train_matrix"]
    user_factors = np.load(user_factors_path)
    item_factors = np.load(item_factors_path)
    return model, user_map, item_map, train_matrix, user_factors, item_factors


def build_test_interactions(test_path: str, user_map: dict, item_map: dict,
                            user_col: str = "user_id", item_col: str = "nid",
                            weight_col: str = "weight") -> csr_matrix:
    """Build test interaction matrix (drops unseen users/items)"""
    df = pd.read_parquet(test_path)
    df = df[df[user_col].isin(user_map) & df[item_col].isin(item_map)]
    rows = df[user_col].map(user_map).values
    cols = df[item_col].map(item_map).values
    data = df[weight_col].values
    return csr_matrix((data, (rows, cols)), shape=(len(user_map), len(item_map)))


def _minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = x.min(), x.max()
    if hi <= lo:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def evaluate_hybrid(
    tfidf_items,
    user_factors: np.ndarray,
    item_factors: np.ndarray,
    train_matrix: csr_matrix,
    test_matrix: csr_matrix,
    alpha: float,
    k_values: list,
    max_users: int = 2000,
) -> dict:
    """Weighted hybrid per user: alpha * content + (1-alpha) * cf.

    Content = cosine profile user (mean TF-IDF item train that was clicked)
    against all items in the ALS item space. Train items are masked so they
    are not recommended again.
    """
    n_users, n_items = test_matrix.shape
    results = {f"{metric}@{k}": [] for metric in ["precision", "recall", "map", "ndcg"] for k in k_values}

    sampled = [u for u in range(n_users) if test_matrix[u].nnz > 0][:max_users]
    for u_idx in sampled:
        train_items = set(train_matrix[u_idx].indices)
        if not train_items:
            continue
        relevant = set(test_matrix[u_idx].indices) - train_items
        if not relevant:
            continue

        profile = tfidf_items[list(train_items)].mean(axis=0)
        content_scores = np.asarray(profile @ tfidf_items.T).ravel()
        cf_scores = user_factors[u_idx] @ item_factors.T
        hybrid_scores = alpha * _minmax(content_scores) + (1 - alpha) * _minmax(cf_scores)
        hybrid_scores[list(train_items)] = -np.inf

        kmax = max(k_values)
        # kth is zero-based; use kmax-1 when selecting exactly kmax candidates.
        top = np.argpartition(-hybrid_scores, kmax - 1)[:kmax]
        top = top[np.argsort(-hybrid_scores[top])]
        recommended = top.tolist()

        for k in k_values:
            rec_k = recommended[:k]
            hits = sum(1 for r in rec_k if r in relevant)
            prec = hits / k if k > 0 else 0
            rec = hits / len(relevant) if relevant else 0

            ap = 0
            hit_count = 0
            for i, r in enumerate(rec_k):
                if r in relevant:
                    hit_count += 1
                    ap += hit_count / (i + 1)
            ap = ap / min(len(relevant), k) if relevant else 0

            def dcg(rels):
                return sum(r / np.log2(i + 2) for i, r in enumerate(rels))

            ideal = sorted([1] * min(len(relevant), k) + [0] * max(0, k - len(relevant)), reverse=True)
            actual = [1 if r in relevant else 0 for r in rec_k]
            ndcg = dcg(actual) / dcg(ideal) if dcg(ideal) > 0 else 0

            results[f"precision@{k}"].append(prec)
            results[f"recall@{k}"].append(rec)
            results[f"map@{k}"].append(ap)
            results[f"ndcg@{k}"].append(ndcg)

    final = {}
    for metric, values in results.items():
        final[metric] = float(np.mean(values)) if values else 0.0
    return final


def train_hybrid(config: dict):
    mcfg = config["model"]
    ccfg = config["components"]
    tcfg = config["train"]
    ecfg = config["eval"]

    print("Loading TF-IDF artifacts...")
    _, tfidf_train_matrix, item_embeddings = load_tfidf_artifacts(
        ccfg["content_model_path"], ccfg["content_embeddings_path"]
    )

    print("Loading ALS artifacts...")
    model, user_map, item_map, als_train_matrix, user_factors, item_factors = load_als_artifacts(
        ccfg["cf_model_path"], ccfg["cf_user_factors_path"], ccfg["cf_item_factors_path"]
    )

    print("Aligning TF-IDF rows to ALS item space...")
    news = pd.read_parquet("data/processed/news_processed.parquet")
    train_nids = news[news["split"] == "train"]["nid"].tolist()
    row_of = {nid: i for i, nid in enumerate(train_nids)}
    inv_item = [None] * len(item_map)
    for nid, idx in item_map.items():
        inv_item[idx] = nid
    tfidf_items = tfidf_train_matrix[[row_of[n] for n in inv_item]].tocsr()
    print(f"TF-IDF aligned: {tfidf_items.shape}")

    print("Loading test interactions...")
    test_matrix = build_test_interactions(
        config["data"]["test_interactions_path"], user_map, item_map
    )

    print(f"TF-IDF train matrix: {tfidf_train_matrix.shape}")
    print(f"User factors: {user_factors.shape}, Item factors: {item_factors.shape}")
    print(f"Train matrix: {als_train_matrix.shape}, Test matrix: {test_matrix.shape}")

    best_alpha = mcfg["content_weight"]
    best_score = -1
    best_results = None

    for alpha in tcfg["alpha_search"]:
        print(f"\nEvaluating alpha={alpha:.1f}...")
        results = evaluate_hybrid(
            tfidf_items, user_factors, item_factors, als_train_matrix,
            test_matrix, alpha, ecfg["k_values"]
        )
        metric_key = tcfg["validation_metric"]
        score = results.get(metric_key, 0)
        print(f"  {metric_key}: {score:.4f}")

        if score > best_score:
            best_score = score
            best_alpha = alpha
            best_results = results

    print(f"\nBest alpha: {best_alpha:.1f} ({tcfg['validation_metric']}: {best_score:.4f})")
    print("Best results:")
    for k, v in best_results.items():
        print(f"  {k}: {v:.4f}")

    out = config["output"]
    Path(out["model_path"]).parent.mkdir(parents=True, exist_ok=True)

    hybrid_artifact = {
        "content_weight": best_alpha,
        "cf_weight": 1 - best_alpha,
        "content_model_path": ccfg["content_model_path"],
        "cf_model_path": ccfg["cf_model_path"],
        "validation_results": best_results,
    }

    with open(out["model_path"], "wb") as f:
        pickle.dump(hybrid_artifact, f)

    with open(out["best_alpha_path"], "w") as f:
        json.dump({"best_alpha": best_alpha, "validation_metric": tcfg["validation_metric"],
                   "results": best_results}, f, indent=2)

    print(f"Saved hybrid config to {out['model_path']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/hybrid.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    train_hybrid(config)


if __name__ == "__main__":
    main()
