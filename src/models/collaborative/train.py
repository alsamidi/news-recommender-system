"""
ALS Collaborative Filtering Training (implicit feedback)
Uses implicit library: https://github.com/benfred/implicit
"""
import argparse
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from scipy.sparse import csr_matrix
import implicit


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def build_interaction_matrix(df: pd.DataFrame, user_col: str, item_col: str, weight_col: str) -> tuple:
    """Build sparse user-item matrix and return (matrix, user_map, item_map)"""
    # Map user/item to indices
    users = df[user_col].unique()
    items = df[item_col].unique()
    user_to_idx = {u: i for i, u in enumerate(users)}
    item_to_idx = {i: idx for idx, i in enumerate(items)}

    rows = df[user_col].map(user_to_idx).values
    cols = df[item_col].map(item_to_idx).values
    data = df[weight_col].values

    matrix = csr_matrix((data, (rows, cols)), shape=(len(users), len(items)))
    return matrix, user_to_idx, item_to_idx


def temporal_split_interactions(df: pd.DataFrame, date_col: str, cutoff: str) -> tuple:
    df[date_col] = pd.to_datetime(df[date_col])
    cutoff_dt = pd.to_datetime(cutoff)
    train = df[df[date_col] < cutoff_dt].copy()
    test = df[df[date_col] >= cutoff_dt].copy()
    return train, test


def filter_min_interactions(df: pd.DataFrame, user_col: str, item_col: str,
                            min_user: int, min_item: int) -> pd.DataFrame:
    """Iteratively filter users/items with too few interactions"""
    while True:
        user_counts = df.groupby(user_col).size()
        item_counts = df.groupby(item_col).size()
        valid_users = user_counts[user_counts >= min_user].index
        valid_items = item_counts[item_counts >= min_item].index
        new_df = df[df[user_col].isin(valid_users) & df[item_col].isin(valid_items)]
        if len(new_df) == len(df):
            break
        df = new_df
    return df


def train_als(config: dict):
    mcfg = config["model"]
    dcfg = config["data"]
    scfg = config["split"]
    ecfg = config["eval"]

    # Load interactions (file-based temporal split per DATASET_LOCK.md)
    train_df = pd.read_parquet(scfg["train_interactions"])
    test_df = pd.read_parquet(scfg["dev_interactions"])

    # Filter sparse users/items on train only
    train_df = filter_min_interactions(
        train_df, dcfg["user_col"], dcfg["item_col"],
        dcfg["min_user_interactions"], dcfg["min_item_interactions"]
    )
    print(f"Train interactions: {len(train_df)}, Test: {len(test_df)}")

    # Build matrices (test reuses train maps; unseen users/items dropped)
    train_matrix, user_map, item_map = build_interaction_matrix(
        train_df, dcfg["user_col"], dcfg["item_col"], dcfg["weight_col"]
    )
    t = test_df[test_df[dcfg["user_col"]].isin(user_map) & test_df[dcfg["item_col"]].isin(item_map)]
    test_matrix = csr_matrix((
        t[dcfg["weight_col"]].values,
        (t[dcfg["user_col"]].map(user_map).values, t[dcfg["item_col"]].map(item_map).values),
    ), shape=train_matrix.shape)

    print(f"Matrix shape: {train_matrix.shape}, Density: {train_matrix.nnz / (train_matrix.shape[0] * train_matrix.shape[1]):.6f}")

    # Train ALS
    model = implicit.als.AlternatingLeastSquares(
        factors=mcfg["factors"],
        regularization=mcfg["regularization"],
        alpha=mcfg["alpha"],
        iterations=mcfg["iterations"],
        use_gpu=mcfg["use_gpu"],
        num_threads=mcfg["num_threads"],
    )

    # implicit.fit expects user-item matrix: rows=users, cols=items (no transpose)
    model.fit(train_matrix.tocsr())

    # Evaluate on test
    if ecfg.get("filter_already_liked", True):
        # Filter out items user already interacted with in train
        pass  # implicit handles this in recommend()

    # Save
    out = config["output"]
    Path(out["model_path"]).parent.mkdir(parents=True, exist_ok=True)

    with open(out["model_path"], "wb") as f:
        pickle.dump({
            "model": model,
            "user_map": user_map,
            "item_map": item_map,
            "train_matrix": train_matrix,
        }, f)

    np.save(out["user_factors_path"], model.user_factors)
    np.save(out["item_factors_path"], model.item_factors)

    print(f"Saved ALS model to {out['model_path']}")
    print(f"User factors: {model.user_factors.shape}, Item factors: {model.item_factors.shape}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/als.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    train_als(config)


if __name__ == "__main__":
    main()