"""View-only interaction generator for the Indo corpus (Gate B).

Behavior model (documented, simulated — no real interactions exist):
  - Each dummy account's latent category profile = catalog base rates
    (category availability) x an idiosyncratic Dirichlet tilt (alpha=0.3
    vector, renormalized). Small relative alpha => concentrated tastes.
    `category_drift` blends in a fresh tilted draw with that probability
    per read (session drift).
  - Item-within-category sampling follows a two-pass power-law scheme:
    pass 1 sees a uniform prior (count=1), pass 2 reweights items by their
    accumulated view counts ** (1/s) — preferential attachment that yields a
    popularity power law; two passes are deemed convergent (plan).
  - `recency_days`: each event's timestamp is drawn uniformly inside the
    window [max(published_at) - recency_days, max(published_at)]; the window
    end is the recency evaluation point for the split.
  - A local numpy Generator seeded from cfg.seed drives every draw: the same
    seed reproduces the output byte-for-byte.

Input contract (plan hard rule #4): metadata only — nid, category, source,
published_at. Any article-text column is a hard error.
"""
import numpy as np
import pandas as pd

from src.phase2 import config

ALLOWED_META = {"nid", "category", "source", "published_at"}
FORBIDDEN_CONTENT = {"content", "processed_text", "title", "abstract"}


def validate_metadata_only(catalog_meta: pd.DataFrame) -> None:
    missing = ALLOWED_META - set(catalog_meta.columns)
    if missing:
        raise ValueError(f"catalog_meta missing metadata columns: {sorted(missing)}")
    leak = set(catalog_meta.columns) & FORBIDDEN_CONTENT
    if leak:
        raise ValueError(f"content columns leaked into generator input: {sorted(leak)}")


def generate_interactions(catalog_meta: pd.DataFrame,
                          cfg: config.GeneratorConfig) -> pd.DataFrame:
    """Simulate view events for dummy accounts; deterministic in cfg.seed.

    Per-account taste profile = catalog base rates (category availability)
    multiplied by an idiosyncratic Dirichlet tilt (alpha=0.3 vector),
    re-normalized. This keeps each account concentrated (one dominant
    category via the tilt) while the POPULATION mixture tracks the catalog
    composition — a plain per-account Dirichlet(a=0.3) makes 600 accounts
    argmax-cover all 17 categories and yields a flat aggregate share
    irrespective of availability (measured 2026-10-27).

    Returns columns: dummy_user_id, nid, event ("view"), occurred_at.
    """
    validate_metadata_only(catalog_meta)
    rng = np.random.default_rng(cfg.seed)
    cats = sorted(catalog_meta["category"].unique().tolist())
    meta = catalog_meta.reset_index(drop=True).copy()
    meta["cat_i"] = meta["category"].map({c: i for i, c in enumerate(cats)})
    # population base rates from catalog availability (EVALUATION ground:
    # category coverage is judged against this mixture)
    cat_counts = meta["category"].value_counts()
    base = np.array([float(cat_counts.get(c, 0)) for c in cats])
    base /= base.sum()
    n_items = len(meta)
    item_cats = meta["cat_i"].to_numpy()
    cat_items = {i: np.flatnonzero(item_cats == i) for i in range(len(cats))}
    pub = pd.to_datetime(meta["published_at"], utc=True)
    max_ns = int(pd.Timestamp(pub.max()).value)
    win_ns = int(cfg.recency_days) * 86_400_000_000_000
    win_start_ns = max_ns - win_ns

    lo, hi = cfg.reads_per_account
    reads = rng.integers(lo, hi + 1, size=cfg.n_accounts)
    total = int(reads.sum())

    uid = np.empty(total, dtype=object)
    nid_i = np.empty(total, dtype=np.int64)
    tstamp = np.empty(total, dtype=np.int64)
    pop = np.ones(n_items, dtype=float)  # pass-1: uniform prior
    pos = 0

    def _tilted_profile() -> np.ndarray:
        """base rates x idiosyncratic tilt, normalized (per fresh profile)."""
        tilt = rng.dirichlet(np.full(len(cats), 0.3)) * len(cats)
        p = base * tilt
        return p / p.sum()

    for acct in range(cfg.n_accounts):
        profile = _tilted_profile()
        for _ in range(int(reads[acct])):
            if rng.random() < cfg.category_drift:
                profile = 0.5 * profile + 0.5 * _tilted_profile()
                profile = profile / profile.sum()
            cat = int(rng.choice(len(cats), p=profile))
            cand = cat_items[cat]
            w = pop[cand] ** (1.0 / max(cfg.powerlaw_s, 1e-9))
            item = int(cand[rng.choice(len(cand), p=w / w.sum())])
            ts = min(win_start_ns + int(rng.integers(0, win_ns + 1)), max_ns) \
                if cfg.recency_days > 0 else max_ns
            uid[pos] = f"dummy_{acct:04d}"
            nid_i[pos] = item
            tstamp[pos] = ts
            pop[item] += 1.0
            pos += 1

    return pd.DataFrame({
        "dummy_user_id": uid,
        "nid": meta["nid"].to_numpy()[nid_i],
        "event": "view",
        "occurred_at": pd.to_datetime(tstamp, utc=True),
    })


def gate_b_report(df: pd.DataFrame,
                  catalog_meta: pd.DataFrame | None = None) -> dict:
    """Fit + validate Gate B statistics on generated interactions."""
    n_items = catalog_meta["nid"].nunique() if catalog_meta is not None \
        else df["nid"].nunique()
    counts = df["nid"].value_counts()

    # Power-law fit on the item view-count rank plot: log(count) vs log(rank).
    counts_sorted = counts.sort_values(ascending=False).to_numpy(dtype=float)
    ranks = np.arange(1, len(counts_sorted) + 1, dtype=float)
    x = np.log(ranks)
    y = np.log(counts_sorted)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    rep = {
        "powerlaw": {"exponent": float(-slope), "r2": float(r2)},
        "item_coverage": {
            "items_ge1_view": float((counts >= 1).sum()) / n_items,
            "items_ge3_views": float((counts >= 3).sum()) / n_items,
            "n_items": int(n_items),
        },
        "accounts": {
            "n_accounts": int(df["dummy_user_id"].nunique()),
            "pct_accounts_ge10_reads": float(
                (df["dummy_user_id"].value_counts() >= 10).mean()),
        },
    }
    if catalog_meta is not None and "category" in catalog_meta.columns:
        profile_mix = catalog_meta["category"].value_counts(normalize=True)
        joined = df.merge(catalog_meta[["nid", "category"]], on="nid", how="left")
        viewed_mix = joined["category"].value_counts(normalize=True)
        rep["category_coverage"] = {
            c: {"profile_share": float(profile_mix.get(c, 0.0)),
                "viewed_share": float(viewed_mix.get(c, 0.0))}
            for c in sorted(set(profile_mix.index) | set(viewed_mix.index))
        }
    return rep
