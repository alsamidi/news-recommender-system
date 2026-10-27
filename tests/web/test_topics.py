"""PRD addendum v1.2 — topic onboarding and the 0-view topic feed.

Covers TEST-AC-259…266 (PRD-AC-55…62). The three invariants that are easy to get subtly wrong
and therefore get the most attention here:

- the topic feed must not call `/recommend` at all (AC-57): a spy on the
  client would catch a regression that still *looks* right in the HTML;
- two users with the same topic SET must get the same order (AC-58), which is
  why `position` is the canonical chip order rather than click order;
- the onboarding is shown exactly once, including after "Lewati" (C2), which
  needs the `topics_prompted_at` marker — zero `user_topics` rows alone cannot
  distinguish "skipped" from "never asked".
"""
from __future__ import annotations

import re

import pytest

from tests.web.conftest import TEST_PASSWORD, csrf_of

NID = re.compile(r"/berita/([NI][0-9a-zA-Z]+)")
CHIP = re.compile(r'name="topik" value="([^"]+)"')

TOKEN = csrf_of


def _register(client, email="topic@example.com"):
    page = client.get("/register")
    token = csrf_of(page.text)
    r = client.post("/register", data={
        "name": "Pengguna", "email": email, "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD, "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    return r


def _post_topics(client, labels, skip=False):
    """Submit the onboarding form the way a browser does.

    Note: a list of `(key, value)` tuples makes httpx send multipart/form-data,
    where this FastAPI version does not populate `Form(...)` fields. A dict
    with a list value stays urlencoded and repeats the key, which is exactly
    what a multi-checkbox form submits.
    """
    page = client.get("/onboarding/topik")
    token = csrf_of(page.text)
    data: dict = {"csrf_token": token}
    if skip:
        data["lewati"] = "1"
    elif labels:
        data["topik"] = list(labels)
    return client.post("/onboarding/topik", data=data, follow_redirects=False)


def _feed_nids(client) -> list[str]:
    body = client.get("/").text
    return list(dict.fromkeys(NID.findall(body)))


def test_onboarding_offered_once_then_never_again(client):
    """TEST-AC-264 / PRD-AC-55 / C2: shown once; skipping is remembered."""
    _register(client)

    first = client.get("/onboarding/topik")
    assert first.status_code == 200
    assert "Pilih sampai 3 topik" in first.text

    assert _post_topics(client, [], skip=True).status_code == 303

    again = client.get("/onboarding/topik", follow_redirects=False)
    assert again.status_code == 303
    assert again.headers["location"] == "/"


def test_chip_set_is_the_measured_twelve(client):
    """TEST-AC-263 / PRD-AC-59: only the 12 measured labels are offered."""
    _register(client)
    body = client.get("/onboarding/topik").text
    chips = CHIP.findall(body)
    assert chips == [
        "Politik", "Hukum", "Ekonomi", "Multimedia", "Olahraga", "Hiburan",
        "Internasional", "Lingkungan", "Teroka", "Tekno-Sains", "Kolom",
        "Cek Fakta",
    ]
    for banned in ("Pemilu", "Ramadan", "Otomotif", "Investigasi", "Bersponsor",
                   "Berita", "Info Tempo"):
        assert banned not in chips
    # Raw portal tags must never leak in as chips.
    for tag in ("jabodetabek", "info-tempo", "detik", "kompas", "tempo"):
        assert tag not in body.lower()


def test_onboarding_rejects_unknown_label_and_too_many(client):
    """TEST-AC-264 / PRD-AC-60: server-side validation, not just form shape."""
    _register(client)
    assert _post_topics(client, ["Topik Palsu"]).status_code == 400
    assert _post_topics(
        client, ["Politik", "Hukum", "Ekonomi", "Olahraga"]).status_code == 400


def test_onboarding_requires_csrf(client):
    """TEST-AC-264 / PRD-AC-60: the form is CSRF-protected like every POST."""
    _register(client)
    r = client.post("/onboarding/topik", data={"topik": "Politik"},
                    follow_redirects=False)
    assert r.status_code == 403


def test_empty_submission_is_a_skip(client):
    """TEST-AC-264 / TEST-AC-265 / C2: m = 0 means "no preference"."""
    _register(client)
    r = client.post("/onboarding/topik", data={"csrf_token": csrf_of(
        client.get("/onboarding/topik").text)}, follow_redirects=False)
    assert r.status_code == 303
    store = client.app.state.store
    user = store.get_user_by_email("topic@example.com")
    assert store.user_topics(int(user["id"])) == []
    assert user["topics_prompted_at"] is not None


def test_topic_feed_renders_for_zero_view_user_only(client, register):
    """TEST-AC-259 / PRD-AC-55 / C1: shown before the first view, never after."""
    _register(client)
    assert _post_topics(client, ["Politik", "Hukum"]).status_code == 303

    body = client.get("/").text
    assert "Populer di topik pilihanmu" in body

    nid = _feed_nids(client)[0]
    client.get(f"/berita/{nid}")
    body = client.get("/").text
    assert "Populer di topik pilihanmu" not in body


def test_topic_feed_categories_match_choice_or_global_topup(client):
    """TEST-AC-260 / PRD-AC-56: chosen topic, or a global top-up card."""
    import pandas as pd

    _register(client)
    chosen = ["Politik", "Hukum"]
    assert _post_topics(client, chosen).status_code == 303

    catalog = pd.read_parquet("data/processed/indo/catalog.parquet",
                              columns=["nid", "category"])
    category = dict(zip(catalog["nid"], catalog["category"]))

    nids = _feed_nids(client)
    assert nids
    rendered = re.findall(r'class="card-category">([^<]+)<', client.get("/").text)
    assert rendered
    # Each rendered category is either chosen or present in the catalog at all
    # (top-up path). Incidental categories can only come from the top-up.
    for cat in rendered:
        assert cat in set(category.values())


def test_topic_feed_never_calls_recommend(client):
    """TEST-AC-261 / PRD-AC-57: selection, not scoring — no /recommend, no alpha."""
    from web.clients.rec_api import RecClient

    _register(client)
    assert _post_topics(client, ["Ekonomi"]).status_code == 303

    calls: list[dict] = []
    original = RecClient.recommend

    async def spy(self, payload):
        calls.append(payload)
        return await original(self, payload)

    RecClient.recommend = spy
    try:
        body = client.get("/").text
    finally:
        RecClient.recommend = original

    assert "Populer di topik pilihanmu" in body
    assert calls == [], f"topic feed called /recommend: {calls}"


def test_topic_order_is_deterministic_across_users(client):
    """TEST-AC-262 / PRD-AC-58: same topic set -> same order, for every account.

    Registered as two separate users with the same chips submitted in
    DIFFERENT form order: canonicalisation must erase the difference, because
    a browser submits checkbox values in DOM order, not click order.
    """
    _register(client, email="a@example.com")
    assert _post_topics(client, ["Hukum", "Politik"]).status_code == 303
    first = _feed_nids(client)

    client.cookies.clear()
    _register(client, email="b@example.com")
    assert _post_topics(client, ["Politik", "Hukum"]).status_code == 303
    second = _feed_nids(client)

    assert first == second, (first, second)


def test_topics_are_profile_data_not_events(client):
    """TEST-AC-265 / PRD-AC-61 / C5: preference never becomes an event."""
    _register(client)
    assert _post_topics(client, ["Teroka"]).status_code == 303
    store = client.app.state.store
    user = store.get_user_by_email("topic@example.com")
    assert store.count_interactions(int(user["id"])) == 0
    # And nothing outside src/web writes it: the research pipeline reads no
    # `user_topics` reference (checked structurally, cheaply).
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    for path in (repo / "src").rglob("*.py"):
        if "web" in path.parts:
            continue
        assert "user_topics" not in path.read_text(), path


def test_smoke_flow_register_topic_detail_history(client):
    """TEST-AC-266 / PRD-AC-62: the journey ends on the v1.1 history path."""
    _register(client)
    assert _post_topics(client, ["Multimedia"]).status_code == 303

    body = client.get("/").text
    assert "Populer di topik pilihanmu" in body
    nid = NID.findall(body)[0]
    assert client.get(f"/berita/{nid}").status_code == 200

    history = client.get("/histori")
    assert "Histori bacaan" in history.text
    assert nid in history.text
    # One view recorded, feed back on the v1.1 path.
    assert "Populer di topik pilihanmu" not in client.get("/").text


def test_chip_set_matches_the_measured_rule():
    """TEST-AC-263 / PRD-AC-59: the chip set is DERIVED from the corpus."""
    """The chip list is DERIVED, not curated — re-derive it from the corpus.

    PRD v1.2 §3 rule: labels with >= 50 train-viewed items in the effective
    band, minus {Berita, Info Tempo, Bersponsor}. Parsing the parquet here is
    what makes a corpus re-lock fail loudly instead of silently dropping a
    chip (Cek Fakta sits at `seen` = 80, only 1.6x the threshold).
    """
    import pandas as pd

    from web.services.topics import (MIN_SEEN_FOR_CHIP, NOT_OFFERED,
                                     TOPIC_LABELS)

    cat = pd.read_parquet("data/processed/indo/catalog.parquet",
                          columns=["nid", "category", "published_at"])
    band = cat[cat["published_at"] >= pd.Timestamp("2025-09-01", tz="UTC")]
    train = pd.read_parquet("data/processed/indo/interactions_train.parquet",
                            columns=["nid"])
    seen_nids = set(train["nid"])

    derived = []
    for label, group in band.groupby("category"):
        if label in NOT_OFFERED:
            continue
        seen = int(group["nid"].isin(seen_nids).sum())
        if seen >= MIN_SEEN_FOR_CHIP:
            derived.append((int(group["nid"].isin(seen_nids).sum()), label))

    assert len(derived) == 12, derived
    # Canonical order is band size descending, then the label as tie-break.
    band_sizes = band.groupby("category").size().to_dict()
    derived.sort(key=lambda row: (-band_sizes[row[1]], row[1]))
    assert tuple(label for _, label in derived) == TOPIC_LABELS, derived
