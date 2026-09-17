"""
Evaluation Script for Recommender Models
Metrics: Precision@K, Recall@K, MAP@K, NDCG@K, Coverage, Diversity
"""
import argparse
import pickle
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def precision_at_k(recommended: list, relevant: set, k: int) -> float:
    if not recommended or k == 0:
        return 0.0
    rec_k = recommended[:k]
    hits = sum(1 for r in rec_k if r in relevant)
    return hits / k


def recall_at_k(recommended: list, relevant: set, k: int) -> float:
    if not relevant:
        return 0.0
    rec_k = recommended[:k]
    hits = sum(1 for r in rec_k if r in relevant)
    return hits / len(relevant)


def ap_at_k(recommended: list, relevant: set, k: int) -> float:
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, r in enumerate(recommended[:k]):
        if r in relevant:
            hits += 1
            score += hits / (i + 1)
    return score / min(len(relevant), k)


def ndcg_at_k(recommended: list, relevant: set, k: int) -> float:
    def dcg(rels):
        return sum(r / np.log2(i + 2) for i, r in enumerate(rels))

    ideal = sorted([1] * len(relevant) + [0] * (k - len(relevant)), reverse=True)
    actual = [1 if r in relevant else 0 for r in recommended[:k]]
    return dcg(actual) / dcg(ideal) if dcg(ideal) > 0 else 0.0


def evaluate_model(model_path: str, test_interactions: csr_matrix, k_values: list,
                   item_features: csr_matrix = None, user_map: dict = None, item_map: dict = None):
    """Evaluate a trained model"""
    with open(model_path, "rb") as f:
        artifact = pickle.load(f)

    model = artifact["model"]
    user_map = artifact.get("user_map", user_map)
    item_map = artifact.get("item_map", item_map)
    inv_item_map = {v: k for k, v in item_map.items()} if item_map else {}

    n_users, n_items = test_interactions.shape
    results = {f"{metric}@{k}": [] for metric in ["precision", "recall", "map", "ndcg"] for k in k_values}

    # For LightFM
    if hasattr(model, "predict"):
        for u_idx in range(min(n_users, 1000)):  # sample users for speed
            user_interactions = test_interactions[u_idx].indices
            if len(user_interactions) == 0:
                continue
            relevant = set(user_interactions)

            # Get scores for all items
            scores = model.predict(u_idx, np.arange(n_items), item_features=item_features)
            recommended = np.argsort(-scores).tolist()

            for k in k_values:
                results[f"precision@{k}"].append(precision_at_k(recommended, relevant, k))
                results[f"recall@{k}"].append(recall_at_k(recommended, relevant, k))
                results[f"map@{k}"].append(ap_at_k(recommended, relevant, k))
                results[f"ndcg@{k}"].append(ndcg_at_k(recommended, relevant, k))

    # For ALS (implicit)
    elif hasattr(model, "recommend"):
        for u_idx in range(min(n_users, 1000)):
            user_interactions = test_interactions[u_idx].indices
            if len(user_interactions) == 0:
                continue
            relevant = set(user_interactions)

            # Get recommendations (filter already liked)
            rec_ids, scores = model.recommend(u_idx, test_interactions[u_idx], N=max(k_values),
                                              filter_already_liked_items=True)
            recommended = rec_ids.tolist()

            for k in k_values:
                results[f"precision@{k}"].append(precision_at_k(recommended, relevant, k))
                results[f"recall@{k}"].append(recall_at_k(recommended, relevant, k))
                results[f"map@{k}"].append(ap_at_k(recommended, relevant, k))
                results[f"ndcg@{k}"].append(ndcg_at_k(recommended, relevant, k))

    # Aggregate
    final = {}
    for metric, values in results.items():
        if values:
            final[metric] = float(np.mean(values))
        else:
            final[metric] = 0.0

    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["tfidf", "als", "hybrid"], required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--split", choices=["temporal", "random"], default="temporal")
    args = parser.parse_args()

    config = load_config(args.config)

    # Load test interactions
    test_path = config["data"].get("test_interactions_path", "data/processed/test_interactions.parquet")
    test_df = pd.read_parquet(test_path)

    # Build test matrix (would need user/item maps from training)
    # This is a skeleton - adapt based on your actual data structure

    # Run evaluation based on model type
    if args.model == "tfidf":
        model_path = config["output"]["model_path"]
        # TF-IDF evaluation would use content similarity
        print("TF-IDF evaluation: compute content similarity for test users")
    elif args.model == "als":
        model_path = config["output"]["model_path"]
        results = evaluate_model(model_path, None, config["eval"]["k_values"])
    elif args.model == "hybrid":
        model_path = config["output"]["model_path"]
        results = evaluate_model(model_path, None, config["eval"]["k_values"])

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()