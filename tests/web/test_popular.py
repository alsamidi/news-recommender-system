"""Popularity ranking: determinism, catalog filtering, failure mode."""
from __future__ import annotations

import pandas as pd
import pytest

from web.services.popular import Popularity, PopularityUnavailable


def frame(nids, weights):
    return pd.DataFrame({"nid": nids, "weight": weights})


def test_ranks_by_weight_desc_then_nid_asc():
    pop = Popularity.from_frame(frame(["N2", "N1", "N3", "N4"], [5, 5, 9, 1]))
    assert pop.top(4) == ["N3", "N1", "N2", "N4"]


def test_sums_duplicate_rows_for_same_nid():
    pop = Popularity.from_frame(frame(["N1", "N1", "N2"], [2, 3, 4]))
    assert pop.top(2) == ["N1", "N2"]


def test_filters_out_non_catalog_nids():
    pop = Popularity.from_frame(
        frame(["N1", "N2", "NX"], [3, 2, 99]), catalog_nids={"N1", "N2"})
    assert pop.top(10) == ["N1", "N2"]


def test_missing_source_raises():
    with pytest.raises(PopularityUnavailable):
        Popularity.build("/nonexistent/path.parquet")


def test_empty_intersection_raises():
    with pytest.raises(PopularityUnavailable):
        Popularity.from_frame(frame(["N1"], [1]), catalog_nids={"OTHER"})


def test_filter_out_keeps_order():
    pop = Popularity(["A", "B", "C", "D"])
    assert pop.filter_out({"B"}).top(10) == ["A", "C", "D"]


def test_real_ranking_is_nonempty_and_deterministic(client):
    """The startup-built ranking exists and repeats identically."""
    pop = client.app.state.popularity
    assert len(pop) > 1000
    assert pop.top(10) == pop.top(10)
    assert len(set(pop.top(100))) == 100
