"""Locked configuration constants for the phase-2 Indo corpus pipeline.

All paths are repo-root relative (repo layout per AGENTS.md). Values mirror
the draft lock `data/DATASET_LOCK_INDO.md`; the generator config dataclass is
frozen so a locked parameter set cannot be mutated mid-pipeline.
"""
from dataclasses import dataclass

RAW_CSV = "data/raw/final_merge_dataset.csv"
CATALOG_OUT = "data/processed/indo/catalog.parquet"
INTERACTIONS_OUT = "data/processed/indo/interactions.parquet"
# Pattern follows metrics_source_of_truth; final path is locked at Gate A.
EVAL_OUT = "models/indo_eval.json"

# Per-source boilerplate phrases stripped during preprocessing (measured from
# real rows; detik/kompas patterns are filled in by task 5 sampling).
BOILERPLATE = {
    "tempo": [
        "Baca berita dengan sedikit iklan",
        "klik di sini",
        "Scroll ke bawah untuk melanjutkan membaca",
    ],
    "detik": [],
    "kompas": [],
}


@dataclass(frozen=True)
class GeneratorConfig:
    """Simulation parameters for the view-only dummy-account generator."""

    n_accounts: int
    reads_per_account: tuple[int, int]  # (min, max)
    powerlaw_s: float                   # popularity exponent
    recency_days: int
    category_drift: float               # prob. of sub-interest drift per session
    seed: int
