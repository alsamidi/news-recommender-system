import dataclasses

from src.phase2.config import (
    BOILERPLATE,
    CATALOG_OUT,
    EVAL_OUT,
    INTERACTIONS_OUT,
    RAW_CSV,
    GeneratorConfig,
)


def test_import_paths():
    assert RAW_CSV == "data/raw/final_merge_dataset.csv"
    assert CATALOG_OUT == "data/processed/indo/catalog.parquet"
    assert INTERACTIONS_OUT == "data/processed/indo/interactions.parquet"
    assert EVAL_OUT == "models/indo_eval.json"
    assert "Baca berita dengan sedikit iklan" in BOILERPLATE["tempo"]


def test_generator_config_frozen():
    cfg = GeneratorConfig(
        n_accounts=10,
        reads_per_account=(5, 20),
        powerlaw_s=1.1,
        recency_days=30,
        category_drift=0.2,
        seed=42,
    )
    try:
        cfg.n_accounts = 11  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("GeneratorConfig must be frozen")
