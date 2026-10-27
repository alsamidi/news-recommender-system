import numpy as np
import pandas as pd
import pytest

from src.phase2 import config
from src.phase2.generator import gate_b_report, generate_interactions


@pytest.fixture(scope="module")
def catalog_meta():
    rng = np.random.default_rng(7)
    n = 200
    return pd.DataFrame({
        "nid": [f"I{i:07d}" for i in range(n)],
        "category": rng.choice(["A", "B", "C", "D", "E"], size=n),
        "source": rng.choice(["tempo", "detik", "kompas"], size=n),
        "published_at": pd.Timestamp("2025-10-01")
        - pd.to_timedelta(rng.integers(0, 400, size=n), unit="D"),
    })


@pytest.fixture(scope="module")
def cfg():
    return config.GeneratorConfig(
        n_accounts=20, reads_per_account=(5, 20), powerlaw_s=1.1,
        recency_days=90, category_drift=0.2, seed=42)


def test_output_schema(catalog_meta, cfg):
    out = generate_interactions(catalog_meta, cfg)
    assert list(out.columns) == ["dummy_user_id", "nid", "event", "occurred_at"]
    assert set(out["event"]) == {"view"}
    assert out["nid"].isin(catalog_meta["nid"]).all()
    assert out["dummy_user_id"].nunique() == cfg.n_accounts


def test_determinism_byte_identical(catalog_meta, cfg):
    a = generate_interactions(catalog_meta, cfg)
    b = generate_interactions(catalog_meta, cfg)
    pd.testing.assert_frame_equal(a, b)  # same seed → identical output
    # differing seed must differ somewhere
    cfg2 = config.GeneratorConfig(**{**cfg.__dict__, "seed": 43})
    c = generate_interactions(catalog_meta, cfg2)
    assert not a.equals(c)


def test_metadata_leak_assert_fires(catalog_meta, cfg):
    leaky = catalog_meta.copy()
    leaky["content"] = "secret"
    with pytest.raises(ValueError, match="leaked"):
        generate_interactions(leaky, cfg)
    with pytest.raises(ValueError, match="missing metadata"):
        generate_interactions(catalog_meta.drop(columns=["published_at"]), cfg)


def test_gate_b_report_keys_and_ranges(catalog_meta, cfg):
    out = generate_interactions(catalog_meta, cfg)
    rep = gate_b_report(out, catalog_meta)
    assert {"powerlaw", "item_coverage", "category_coverage", "accounts"} \
        <= set(rep)
    assert 0 <= rep["powerlaw"]["exponent"] < 5
    assert 0.0 <= rep["powerlaw"]["r2"] <= 1.0
    cov = rep["item_coverage"]
    assert cov["n_items"] == 200
    assert 0.0 <= cov["items_ge1_view"] <= 1.0
    assert 0.0 <= cov["items_ge3_views"] <= cov["items_ge1_view"]
    acc = rep["accounts"]
    assert acc["n_accounts"] == 20
    assert 0.0 <= acc["pct_accounts_ge10_reads"] <= 1.0
    # profile vs viewed shares present per category
    assert set(rep["category_coverage"]) == {"A", "B", "C", "D", "E"}
