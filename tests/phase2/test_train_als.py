import numpy as np
import pandas as pd
import pytest

from src.phase2.train_als import ALS_PARAMS, build_csr, gate_c_report


@pytest.fixture()
def train_events():
    rng = np.random.default_rng(0)
    rows = []
    for u in range(4):
        for _ in range(6):
            rows.append((f"u{u}", f"I{int(rng.integers(0, 9)):03d}"))
    return pd.DataFrame(rows, columns=["dummy_user_id", "nid"])


def test_build_csr_shapes_and_confidence(train_events):
    mat, uidx, iidx = build_csr(train_events)
    assert mat.shape[0] == 4
    assert mat.shape[1] == 8
    # duplicate (u, nid) pairs: 24 events -> some repeats; confidence 1+40*r
    r = train_events.groupby(["dummy_user_id", "nid"], observed=True).size()
    assert mat.nnz == len(r)
    u, n = r.index[0]
    expected_conf = 1 + ALS_PARAMS["alpha"] * r.iloc[0]
    assert mat[uidx[u], iidx[n]] == pytest.approx(expected_conf)


def test_build_csr_deterministic_id_order(train_events):
    _, uidx1, iidx1 = build_csr(train_events)
    shuffled = train_events.sample(frac=1.0, random_state=3)
    _, uidx2, iidx2 = build_csr(shuffled)
    assert uidx1 == uidx2 and iidx1 == iidx2


def test_gate_c_report_ranges(train_events):
    mat, uidx, iidx = build_csr(train_events)

    class FakeModel:
        user_factors = np.zeros((4, 8))
        item_factors = np.zeros((8, 8))

    rep = gate_c_report(FakeModel(), mat, n_effective_items=8)
    assert rep["item_factor_coverage"] == 1.0
    assert rep["account_factor_coverage"] == 1.0
    assert rep["params"] == ALS_PARAMS


def test_real_als_fit_smoke(train_events):
    from src.phase2.train_als import fit_als
    mat, uidx, iidx = build_csr(train_events)
    model = fit_als(mat)
    assert model.item_factors.shape == (8, ALS_PARAMS["factors"])
    assert model.user_factors.shape == (4, ALS_PARAMS["factors"])
