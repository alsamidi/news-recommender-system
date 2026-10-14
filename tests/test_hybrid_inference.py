"""Parity tests: serving inference == frozen Day 4/5 evaluators (P1).

The oracle in each test assembles the evaluator's own primitives
independently; the recommender must reproduce the exact ranking.
"""
import numpy as np
import pandas as pd
import pytest

from evaluation.full_catalog_eval import (
    _minmax,
    _topk_sorted,
    expand_cf_scores,
    precompute_user_scores,
)
from evaluation.stratified_eval import pseudo_user_factor
from models.hybrid.infer import HybridRecommender, UnknownUserError, serving_alpha

ALPHA = 0.4
TOP_K = 10


@pytest.fixture(scope="module")
def recommender():
    return HybridRecommender.load()  # frozen artifacts, ~7s once


def eligible_users(d, n=3):
    elig = sorted(u for u in d["train_full"]
                  if u in d["dev_full"] and (d["dev_full"][u] - d["train_full"][u]))
    return elig[:n]


def test_serving_alpha_is_final_04(recommender):
    assert serving_alpha() == ALPHA == recommender.alpha


def test_serving_alpha_matches_table_b_winner():
    """Serving alpha must equal the evaluated full-catalog winner (P3.1)."""
    import json
    rows = json.load(open("models/full_catalog_eval.json"))["table_b_full_catalog"]
    winner = max(rows, key=lambda r: r["ndcg@10"])["alpha"]
    assert serving_alpha() == winner == ALPHA


def dedupe_positions(d, rec, top_k=TOP_K):
    """Presentation rule shared with HybridRecommender._select (test copy)."""
    seen, out = set(), []
    for i in rec:
        nid = d["full_nids"][i]
        if nid not in seen:
            seen.add(nid)
            out.append(i)
        if len(out) == top_k:
            break
    return out


def test_warm_parity_topk_and_scores(recommender):
    d = recommender._d
    n_full = len(d["full_nids"])
    for uid in eligible_users(d):
        ti = d["train_full"][uid]
        c_norm, cf_norm = precompute_user_scores([uid], d)[uid]  # evaluator oracle
        cf_full = expand_cf_scores(cf_norm, d["als_full_pos"], n_full, ALPHA)
        s = ALPHA * c_norm + (1 - ALPHA) * cf_full
        # serving mask policy: nid-level (see HybridRecommender._mask_seen)
        seen = {d["full_nids"][i] for i in ti}
        s[[p for n in seen for p in recommender._pos_of_nid[n]]] = -np.inf
        expected_idx = dedupe_positions(d, _topk_sorted(s, 2 * TOP_K))
        got = recommender.recommend_user(uid, top_k=TOP_K)
        assert [a["nid"] for a in got] == [d["full_nids"][i] for i in expected_idx]
        assert len({a["nid"] for a in got}) == TOP_K, "duplicate nids served"
        assert np.allclose([a["score"] for a in got], [s[i] for i in expected_idx])
        assert not (set(a["nid"] for a in got)
                    & {d["full_nids"][i] for i in ti}), "train items leaked"


def test_warm_unknown_user_raises(recommender):
    with pytest.raises(UnknownUserError):
        recommender.recommend_user("U000000_nope", top_k=5)


def cold_session(d):
    dv = pd.read_parquet("data/processed/interactions_dev.parquet")
    dv = dv.sort_values(["user_id", "time"])
    cold = dv[~dv["user_id"].isin(set(d["user_map"]))]
    for uid, g in cold.groupby("user_id"):
        nids = g["nid"].tolist()
        if len(nids) >= 2 and nids[-1] in d["nid_to_full"]:
            hist = nids[:-1]
            if any(n in d["item_map"] for n in hist):
                return hist
    raise AssertionError("no cold session fixture found")


def cold_oracle(d, hist, pos_of):
    n2f = d["nid_to_full"]
    ti = {n2f[n] for n in hist if n in n2f}
    prof = d["full_tfidf"][sorted(ti)].mean(axis=0)
    c = _minmax(np.asarray(prof @ d["full_tfidf"].T).ravel()).astype(np.float32)
    pu = pseudo_user_factor(list(hist), d["item_map"], d["item_factors"])
    assert pu is not None
    cf_full = np.zeros(len(d["full_nids"]), dtype=np.float64)
    cf_full[d["als_full_pos"]] = _minmax(pu @ d["item_factors"].T).astype(np.float32)
    s = ALPHA * c.astype(np.float64) + (1 - ALPHA) * cf_full
    # serving mask policy: nid-level (see HybridRecommender._mask_seen)
    seen = {n for n in hist if n in n2f}
    s[[p for n in seen for p in pos_of[n]]] = -np.inf
    return dedupe_positions(d, _topk_sorted(s, 2 * TOP_K)), s


def test_cold_parity_topk(recommender):
    d = recommender._d
    hist = cold_session(d)
    expected_idx, s = cold_oracle(d, hist, recommender._pos_of_nid)
    got = recommender.recommend_session(hist, top_k=TOP_K)
    assert [a["nid"] for a in got] == [d["full_nids"][i] for i in expected_idx]
    assert len({a["nid"] for a in got}) == TOP_K, "duplicate nids served"
    assert np.allclose([a["score"] for a in got], [s[i] for i in expected_idx])
    assert not ({a["nid"] for a in got} & set(hist)), "session items leaked"


def test_cold_fallback_no_als_item_is_pure_content(recommender):
    d = recommender._d
    n2f = d["nid_to_full"]
    no_als = [n for n in d["full_nids"] if n not in d["item_map"]][:3]
    assert pseudo_user_factor(no_als, d["item_map"], d["item_factors"]) is None
    got = recommender.recommend_session(no_als, top_k=TOP_K)
    ti = {n2f[n] for n in no_als}
    prof = d["full_tfidf"][sorted(ti)].mean(axis=0)
    c = _minmax(np.asarray(prof @ d["full_tfidf"].T).ravel()).astype(np.float64)
    c[[p for n in no_als for p in recommender._pos_of_nid[n]]] = -np.inf
    expected_idx = dedupe_positions(d, _topk_sorted(c, 2 * TOP_K))
    assert [a["nid"] for a in got] == [d["full_nids"][i] for i in expected_idx]


def test_session_errors(recommender):
    with pytest.raises(ValueError):
        recommender.recommend_session([], top_k=5)
    with pytest.raises(ValueError):
        recommender.recommend_session(["N000_nope"], top_k=5)


@pytest.fixture(scope="module")
def client(recommender):
    import api.main as api_main
    from fastapi.testclient import TestClient
    api_main.rec = recommender  # reuse module fixture, skip second load
    return TestClient(api_main.app)


def test_api_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["alpha"] == ALPHA and body["catalog_size"] == 93698


def test_api_recommend_warm(client, recommender):
    uid = eligible_users(recommender._d, n=1)[0]
    r = client.post("/recommend", json={"user_id": uid, "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "warm" and body["alpha"] == ALPHA
    assert all({"nid", "title", "category", "subcategory", "score"} <= set(a)
               for a in body["recommendations"]), "metadata incomplete"
    assert [a["nid"] for a in body["recommendations"]] == \
        [a["nid"] for a in recommender.recommend_user(uid, top_k=5)]


def test_api_recommend_cold_and_errors(client, recommender):
    hist = cold_session(recommender._d)
    r = client.post("/recommend", json={"history": hist, "top_k": 5})
    assert r.status_code == 200 and r.json()["mode"] == "cold-session"
    assert client.post("/recommend", json={"user_id": "U000000_nope"}).status_code == 404
    assert client.post("/recommend", json={"top_k": 5}).status_code == 400
    hist = cold_session(recommender._d)
    uid = eligible_users(recommender._d, n=1)[0]
    r = client.post("/recommend", json={"user_id": uid, "history": hist})
    assert r.status_code == 400, "ambiguous warm+cold input must be rejected"


def test_similar_excludes_self_and_ranks_desc(recommender):
    nid = recommender._d["full_nids"][0]
    got = recommender.similar(nid, top_k=5)
    assert len(got) == 5 and len({a["nid"] for a in got}) == 5
    assert nid not in {a["nid"] for a in got}
    scores = [a["score"] for a in got]
    assert all(b <= a for a, b in zip(scores, scores[1:]))
    assert recommender.article(nid)["nid"] == nid


def test_openapi_contract_surface():
    """Frozen contract surface (P3.1): exactly these 4 routes, these schemas."""
    import api.main as api_main
    spec = api_main.app.openapi()
    assert set(spec["paths"]) == {"/health", "/recommend",
                                  "/similar/{nid}", "/article/{nid}"}
    assert spec["paths"]["/recommend"]["post"]["requestBody"]["content"] \
        ["application/json"]["schema"]["$ref"] == "#/components/schemas/RecommendRequest"
    for name in ("RecommendRequest", "RecommendResponse", "ArticleResponse",
                 "HealthResponse", "SimilarResponse", "ArticleDetailResponse"):
        assert name in spec["components"]["schemas"], name
    req_props = spec["components"]["schemas"]["RecommendRequest"]["properties"]
    assert "alpha" not in req_props, "per-request alpha override breaks the freeze"
    assert req_props["top_k"]["maximum"] == 100
    assert "/" not in spec["paths"], "demo viewer must stay out of the API schema"


def test_demo_presets_from_frozen_artifacts(recommender):
    import api.main as api_main
    p = api_main.resolve_presets(recommender._d)
    d = recommender._d
    assert p["warm_user"] in d["user_map"]
    assert len(p["cold_session"]) >= 2
    assert any(n in d["item_map"] for n in p["cold_session"])
    assert len(p["fallback_session"]) == 3
    assert all(n in d["nid_to_full"] and n not in d["item_map"]
               for n in p["fallback_session"])


def test_demo_ui_serves_presets(client, recommender):
    import api.main as api_main
    api_main.demo_presets = api_main.resolve_presets(recommender._d)
    r = client.get("/")
    assert r.status_code == 200
    assert "Indonesian News Recommender" in r.text
    assert api_main.demo_presets["warm_user"] in r.text
    assert 'fetch("/recommend"' in r.text
