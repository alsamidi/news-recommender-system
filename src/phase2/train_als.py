"""ALS training on simulated dummy-account interactions (Gate C).

CSR matrix: dummy_user x nid from TRAIN interactions only.
`implicit.als.AlternatingLeastSquares` with the v1 research defaults
(factors=128, regularization=0.01, iterations=20; confidence
c = 1 + alpha*r with alpha=40, r = number of views). Seed forced per call.
Artifacts (gitignored): models/indo_als_model.pkl,
models/indo_als_user_factors.npy, models/indo_als_item_factors.npy —
identity recorded in the lock via sha256.
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from implicit.als import AlternatingLeastSquares

REPO = Path(__file__).resolve().parents[2]
ALS_PARAMS = {"factors": 128, "regularization": 0.01, "iterations": 20,
              "alpha": 40.0, "seed": 42}
ALS_SEED = 42


def build_csr(train_events: pd.DataFrame):
    """CSR [n_users, n_items] with confidence weights c = 1 + alpha * views.

    Rows/columns use the sorted unique ids (categorical order), returned as
    explicit id->index maps so evaluation can index deterministically.
    """
    user_ids = sorted(train_events["dummy_user_id"].unique())
    item_ids = sorted(train_events["nid"].unique())
    uidx = {u: i for i, u in enumerate(user_ids)}
    iidx = {n: i for i, n in enumerate(item_ids)}
    r = (train_events.groupby(["dummy_user_id", "nid"], observed=True)
         .size().rename("views").reset_index())
    rows = r["dummy_user_id"].map(uidx).to_numpy()
    cols = r["nid"].map(iidx).to_numpy()
    conf = 1.0 + ALS_PARAMS["alpha"] * r["views"].to_numpy(dtype=float)
    mat = sp.csr_matrix((conf, (rows, cols)),
                        shape=(len(user_ids), len(item_ids)))
    return mat, uidx, iidx


def fit_als(mat: sp.csr_matrix) -> AlternatingLeastSquares:
    model = AlternatingLeastSquares(
        factors=ALS_PARAMS["factors"],
        regularization=ALS_PARAMS["regularization"],
        iterations=ALS_PARAMS["iterations"],
        random_state=ALS_SEED,
    )
    model.fit(mat)  # implicit treats values as confidence
    return model


def gate_c_report(model, mat: sp.csr_matrix,
                  n_effective_items: int) -> dict:
    """Coverage of ALS factors over effective items and accounts."""
    items_with_factors = int(np.isfinite(model.item_factors).all(axis=1).sum())
    users_with_factors = int(np.isfinite(model.user_factors).all(axis=1).sum())
    return {
        "item_factor_coverage": items_with_factors / n_effective_items,
        "account_factor_coverage": users_with_factors / mat.shape[0],
        "items_with_factors": items_with_factors,
        "n_effective_items": int(n_effective_items),
        "accounts_with_factors": users_with_factors,
        "n_accounts": int(mat.shape[0]),
        "params": ALS_PARAMS,
    }


def save_artifacts(model, out_dir: Path | None = None) -> dict:
    out = Path(out_dir) if out_dir else REPO / "models"
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "model": out / "indo_als_model.pkl",
        "user_factors": out / "indo_als_user_factors.npy",
        "item_factors": out / "indo_als_item_factors.npy",
    }
    with open(paths["model"], "wb") as f:
        pickle.dump(model, f)
    np.save(paths["user_factors"], model.user_factors)
    np.save(paths["item_factors"], model.item_factors)
    return paths
