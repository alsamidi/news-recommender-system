import numpy as np
import pandas as pd
import pytest

from src.phase2.evaluate import (ALPHA_GRID, ap_at_k, build_tfidf, cbf_ranker,
                                 evaluate_point, evaluate_ranking, f1_at_k,
                                 minmax, ndcg_at_k, popularity_ranker,
                                 precision_at_k, recall_at_k, rank_topk)


def test_metric_math_hand_computed():
    ranked = ["x1", "x2", "x3", "x4", "x5"]
    rel = {"x2", "x4"}
    # NDCG@10: DCG = 1/log2(3) + 1/log2(5); IDCG = 1/log2(2) + 1/log2(3)
    assert ndcg_at_k(ranked, rel, 10) == pytest.approx(
        (1 / np.log2(3) + 1 / np.log2(5)) / (1 / np.log2(2) + 1 / np.log2(3)))
    # a perfect ordering under the same relevance set scores 1.0
    assert ndcg_at_k(["x2", "x4", "x1", "x3", "x5"], rel, 10) == pytest.approx(1.0)
    # Recall@5 = 2/2 = 1
    assert recall_at_k(ranked, rel, 5) == pytest.approx(1.0)
    # AP@5 = (1/2 + 2/4)/2 = 0.5
    assert ap_at_k(ranked, rel, 5) == pytest.approx(0.5)

    ranked2 = ["x1", "z1", "z2", "x2", "z3", "z4", "z5", "z6", "z7", "z8"]
    rel2 = {"x2", "x9"}
    # NDCG@10: DCG = 1/log2(5) = 0.43068; IDCG = 1/log2(2)+1/log2(3) = 1.63093
    assert ndcg_at_k(ranked2, rel2, 10) == pytest.approx(
        (1 / np.log2(5)) / (1 / np.log2(2) + 1 / np.log2(3)))
    # AP@10 = (1/4)/min(2,10) = 0.125; Recall = 1/2; one relevant in top-10
    assert ap_at_k(ranked2, rel2, 10) == pytest.approx(0.125)
    assert recall_at_k(ranked2, rel2, 10) == pytest.approx(0.5)


def test_metric_edge_cases():
    assert ndcg_at_k([], {"x"}, 10) == 0.0
    assert recall_at_k(["x"], set(), 10) == 0.0
    assert ap_at_k(["x", "y"], {"x", "y"}, 10) == pytest.approx(1.0)


def test_precision_and_f1_hand_computed():
    ranked = ["x1", "x2", "x3", "x4", "x5"]
    rel = {"x2", "x4"}
    # two of the five ranked items are relevant
    assert precision_at_k(ranked, rel, 5) == pytest.approx(0.4)
    assert f1_at_k(ranked, rel, 5) == pytest.approx(2 * 0.4 * 1.0 / 1.4)

    ranked2 = ["x1", "z1", "z2", "x2", "z3", "z4", "z5", "z6",
               "z7", "z8"]
    rel2 = {"x2", "x9"}
    assert precision_at_k(ranked2, rel2, 10) == pytest.approx(0.1)
    assert f1_at_k(ranked2, rel2, 10) == pytest.approx(2 * 0.1 * 0.5 / 0.6)
    # no prediction and no relevant item are both scored as zero
    assert precision_at_k([], rel2, 10) == 0.0
    assert precision_at_k(ranked2, set(), 10) == 0.0
    assert f1_at_k(ranked2, set(), 10) == 0.0


def test_f1_is_the_harmonic_mean_and_map_is_ap():
    for ranked, rel in ((["a", "b", "c"], {"b"}),
                        (["a", "b", "c"], {"a", "c"}),
                        (["a", "b"], set())):
        p = precision_at_k(ranked, rel, 10)
        r = recall_at_k(ranked, rel, 10)
        want = 0.0 if p + r == 0 else 2 * p * r / (p + r)
        assert f1_at_k(ranked, rel, 10) == pytest.approx(want)
        top = ranked[:10]
        assert precision_at_k(ranked, rel, 10) * len(top) == pytest.approx(
            sum(1 for nid in top if nid in rel))


def test_evaluate_ranking_reports_five_metrics_at_the_cutoff():
    ranked = ["x1", "x2", "x3"]
    rel = {"x2"}
    row = evaluate_ranking(ranked, rel, 5)
    assert set(row) == {"ndcg@5", "ap@5", "map@5", "precision@5",
                        "recall@5", "f1@5", "n_relevant"}
    assert row["map@5"] == row["ap@5"]
    assert row["precision@5"] == pytest.approx(1 / 3)
    assert row["recall@5"] == pytest.approx(1.0)
    assert row["n_relevant"] == 1


def _toy_catalog(n_items=50, n_train=40):
    rng = np.random.default_rng(11)
    nids = [f"I{i:03d}" for i in range(n_items)]
    # two clean topics: even ids topic words A, odd ids topic words B
    texts = [("alpha alpha alpha topic%d" % i) if i % 2 == 0
             else ("beta beta beta topic%d" % i) for i in range(n_items)]
    pub = pd.Timestamp("2025-06-01", tz="UTC") + pd.to_timedelta(
        rng.integers(0, 30, n_items), unit="D")
    cat = pd.DataFrame({
        "nid": nids,
        "title": [f"t{i}" for i in range(n_items)],
        "content": texts,
        "processed_text": texts,
        "category": ["A" if i % 2 == 0 else "B" for i in range(n_items)],
        "source": "tempo",
        "published_at": pub,
    })
    return cat.iloc[:n_train].reset_index(drop=True), cat, nids


def test_popularity_ranker_hand_order():
    cat_train, cat_full, nids = _toy_catalog()
    train_events = pd.DataFrame({
        "dummy_user_id": ["u1"] * 6,
        "nid": ["I000", "I000", "I002", "I002", "I002", "I004"],
    })
    # counts: I000=2, I002=3, I004=1; restricted dev = zero-count dev items
    dev = sorted(set(nids) - {"I000", "I002", "I004"})
    score_fn = popularity_ranker(train_events, dev)
    ranked = rank_topk(score_fn, dev, ["u1"], k=10)["u1"]
    # all dev items zero-count -> nid asc (stable)
    assert ranked == dev[:10]


def test_cbf_scores_topic_alignment():
    cat_train, cat_full, nids = _toy_catalog()
    vec, mat = build_tfidf(cat_train, cat_full)
    row_of = {n: i for i, n in enumerate(cat_full["nid"])}
    # account u read ONLY topic-A (even) train items
    train_events = pd.DataFrame({
        "dummy_user_id": ["u1"] * 3,
        "nid": ["I000", "I002", "I004"],
    })
    dev = [n for n in nids]
    fn = cbf_ranker(mat, row_of, train_events, dev)
    s = fn("u1")
    s_by = dict(zip(dev, s))
    evens = [s_by[n] for n in nids if int(n[1:]) % 2 == 0]
    odds = [s_by[n] for n in nids if int(n[1:]) % 2 == 1]
    assert np.mean(evens) > np.mean(odds)  # profile aligns with topic A


def test_evaluate_point_smoke_and_hybrid_keys():
    from src.phase2.train_als import build_csr, fit_als
    cat_train, cat_full, nids = _toy_catalog(50, 40)
    # toy interaction world: 2 accounts, repeated views so ALS has factors
    train_events = pd.DataFrame([
        ("u1", "I000"), ("u1", "I002"), ("u1", "I000"),
        ("u2", "I001"), ("u2", "I003"), ("u2", "I001"),
    ], columns=["dummy_user_id", "nid"])
    dev_events = pd.DataFrame([
        ("u1", "I010"), ("u1", "I012"), ("u2", "I011"),
    ], columns=["dummy_user_id", "nid"])
    mat, uidx, iidx = build_csr(train_events)
    model = fit_als(mat)

    rep = evaluate_point(cat_full, cat_train, train_events, dev_events,
                         als_model=model, uidx=uidx, iidx=iidx)
    assert "popularity" in rep and "cbf" in rep and "als" in rep
    assert all(f"hybrid_a{a}" in rep for a in ALPHA_GRID)
    for name, row in rep.items():
        assert 0.0 <= row["ndcg@10_mean"] <= 1.0
        assert 0.0 <= row["ap@10_mean"] <= 1.0
        assert 0.0 <= row["recall@10_mean"] <= 1.0


def test_hybrid_alpha_extremes_track_components():
    als = np.array([5.0, 4.0, 1.0, 0.0])
    cbf = np.array([0.0, 3.0, 4.0, 5.0])
    a, b = minmax(als), minmax(cbf)
    hi = 0.8 * a + 0.2 * b
    lo = 0.2 * a + 0.8 * b
    assert np.argmax(hi) == 0 == np.argmax(a)          # alpha->1 follows als
    assert np.argmax(lo) == 3 == np.argmax(cbf)        # alpha->0 follows cbf
