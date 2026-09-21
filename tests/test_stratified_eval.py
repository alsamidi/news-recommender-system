"""Tests for stratified warm/cold evaluation helpers."""
import numpy as np

from evaluation.stratified_eval import (
    pseudo_user_factor,
    popularity_full_vector,
    split_session,
)
def test_split_session_leave_last_out():
    assert split_session(["a", "b", "c"]) == (["a", "b"], "c")


def test_split_session_too_short():
    assert split_session(["a"]) is None
    assert split_session([]) is None


def test_pseudo_user_factor_mean_of_known_rows():
    item_map = {"n1": 0, "n2": 1}
    itf = np.array([[1.0, 0.0], [0.0, 1.0], [9.0, 9.0]])
    pseudo = pseudo_user_factor(["n1", "n2", "nx"], item_map, itf)
    assert np.allclose(pseudo, [0.5, 0.5])


def test_pseudo_user_factor_none_when_no_session_item_in_als():
    assert pseudo_user_factor(["nx", "ny"], {"n1": 0}, np.zeros((1, 2))) is None


def test_popularity_full_vector_maps_counts_to_catalog_positions():
    nid_to_full = {"n1": 5, "n2": 2}
    v = popularity_full_vector({"n1": 3, "n2": 7, "nx": 2}, nid_to_full, 10)
    assert v[5] == 3 and v[2] == 7
    assert v.sum() == 10  # nid di luar katalog diabaikan
