"""
TF-IDF Content-Based Baseline Training
"""
import argparse
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def temporal_split(df: pd.DataFrame, date_col: str, cutoff: str) -> tuple:
    df[date_col] = pd.to_datetime(df[date_col])
    cutoff_dt = pd.to_datetime(cutoff)
    train = df[df[date_col] < cutoff_dt].copy()
    test = df[df[date_col] >= cutoff_dt].copy()
    return train, test


def train_tfidf(config: dict):
    cfg = config["model"]["vectorizer"]
    vectorizer = TfidfVectorizer(
        ngram_range=tuple(cfg["ngram_range"]),
        max_features=cfg["max_features"],
        min_df=cfg["min_df"],
        max_df=cfg["max_df"],
        sublinear_tf=cfg["sublinear_tf"],
        norm=cfg["norm"],
    )

    # Load processed data
    data_path = config.get("data", {}).get("processed_path", "data/processed/news_processed.parquet")
    df = pd.read_parquet(data_path)

    # Temporal split (file-based via split column per DATASET_LOCK.md,
    # fallback to date column for other datasets)
    split_cfg = config.get("train", {})
    cutoff = split_cfg.get("temporal_split_date", "2019-11-15")
    date_col = split_cfg.get("date_column", "publish_date")
    if date_col in df.columns:
        train_df, test_df = temporal_split(df, date_col, cutoff)
    else:
        train_df = df[df["split"] == "train"].copy()
        test_df = df[df["split"] == "dev"].copy()

    print(f"Train: {len(train_df)}, Test: {len(test_df)}")

    # Fit on train
    train_texts = train_df["processed_text"].fillna("").tolist()
    tfidf_matrix = vectorizer.fit_transform(train_texts)

    # Transform test
    test_texts = test_df["processed_text"].fillna("").tolist()
    test_tfidf = vectorizer.transform(test_texts)

    # Save artifacts
    out = config["output"]
    Path(out["model_path"]).parent.mkdir(parents=True, exist_ok=True)

    with open(out["model_path"], "wb") as f:
        pickle.dump({"vectorizer": vectorizer, "train_matrix": tfidf_matrix}, f)

    np_save = out["embeddings_path"]
    if np_save.endswith(".npz"):
        from scipy.sparse import save_npz
        save_npz(np_save, tfidf_matrix.tocsr())
    else:
        np.save(np_save, tfidf_matrix.toarray())
    with open(out["vectorizer_path"], "wb") as f:
        pickle.dump(vectorizer, f)

    print(f"Vocab size: {len(vectorizer.vocabulary_)}")
    print(f"Train matrix shape: {tfidf_matrix.shape}")
    print(f"Saved to {out['model_path']}")

    # Quick similarity sanity check
    sims = cosine_similarity(tfidf_matrix[:5], tfidf_matrix[:5])
    print(f"Sample similarity matrix (5x5):\n{sims.round(3)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/tfidf_baseline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    train_tfidf(config)


if __name__ == "__main__":
    main()