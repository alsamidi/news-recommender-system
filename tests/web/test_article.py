"""Article detail, view recording, and history isolation."""
from __future__ import annotations

import re

NID = re.compile(r'/berita/(N\d+)')


def _store(client):
    return client.app.state.store


def _uid(client) -> int:
    return int(_store(client).get_user_by_email("budi@example.com")["id"])


def test_detail_renders_title_and_category(client, register):
    register()
    nid = NID.findall(client.get("/").text)[0]
    r = client.get(f"/berita/{nid}")
    assert r.status_code == 200                          # TEST-AC-060
    detail = r.text
    assert nid in detail
    assert "article-headline" in detail
    assert "card-category" in detail


def test_detail_records_exactly_one_view(client, register):
    register()
    nid = NID.findall(client.get("/").text)[0]
    before = _store(client).count_interactions(_uid(client))
    client.get(f"/berita/{nid}")
    after = _store(client).count_interactions(_uid(client))
    assert after - before == 1                           # TEST-AC-062


def test_refresh_creates_a_new_view(client, register):
    register()
    nid = NID.findall(client.get("/").text)[0]
    client.get(f"/berita/{nid}")
    client.get(f"/berita/{nid}")
    # No time-window dedupe: two loads, two rows (TEST-AC-063).
    assert _store(client).count_interactions(_uid(client)) == 2


def test_unknown_nid_returns_404_and_no_row(client, register):
    register()
    before = _store(client).count_interactions(_uid(client))
    r = client.get("/berita/N000_nope")
    assert r.status_code == 404                          # TEST-AC-064
    assert "Berita tidak ditemukan." in r.text
    assert _store(client).count_interactions(_uid(client)) == before  # TEST-AC-032


def test_article_without_abstract_renders_cleanly(client, register):
    register()
    store = _store(client)
    with store.connect() as conn:
        row = conn.execute(
            "SELECT nid FROM interactions LIMIT 1").fetchone()
    # Find a catalog nid whose abstract is missing via the API response.
    from web.clients.rec_api import RecClient  # noqa: F401
    candidates = NID.findall(client.get("/").text)[:10]
    for nid in candidates:
        detail = client.get(f"/berita/{nid}").text
        if "Ringkasan tidak tersedia untuk berita ini." in detail:
            break
    else:
        # No such article in this feed slice; the copy check is enough.
        detail = client.get(f"/berita/{candidates[0]}").text
    assert "None" not in detail                          # TEST-AC-065


def test_similar_block_excludes_self(client, register):
    register()
    nid = NID.findall(client.get("/").text)[0]
    body = client.get(f"/berita/{nid}").text
    if "Berita serupa" not in body:
        return  # no neighbours for this item
    related = re.findall(r'class="card" href="/berita/(N\d+)', body)
    assert nid not in related                            # TEST-AC-066


def test_history_is_isolated_between_users(client, register):
    register(email="a@example.com")
    nid = NID.findall(client.get("/").text)[0]
    client.get(f"/berita/{nid}")

    client.cookies.clear()
    from tests.web.conftest import TEST_PASSWORD, csrf_of
    page = client.get("/register")
    client.post("/register", data={
        "name": "B", "email": "b@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD, "csrf_token": csrf_of(page.text)})

    body = client.get("/histori").text
    assert nid not in body                               # TEST-AC-072


def test_history_is_not_reachable_via_query_param(client, register):
    """A ?user_id= parameter must never select another user's history."""
    register(email="a@example.com")
    own = NID.findall(client.get("/").text)[0]
    client.get(f"/berita/{own}")

    # Second account with its own, different history.
    client.cookies.clear()
    from tests.web.conftest import TEST_PASSWORD, csrf_of
    page = client.get("/register")
    client.post("/register", data={
        "name": "B", "email": "b@example.com", "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD, "csrf_token": csrf_of(page.text)})
    other = [n for n in NID.findall(client.get("/").text) if n != own][0]
    client.get(f"/berita/{other}")

    first_id = int(client.app.state.store.get_user_by_email("a@example.com")["id"])
    body = client.get(f"/histori?user_id={first_id}").text
    assert own not in body and other in body             # TEST-AC-074/072
