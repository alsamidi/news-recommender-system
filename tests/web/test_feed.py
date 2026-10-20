"""Feed routing, filtering, and source labelling."""
from __future__ import annotations

import re

from web.clients.rec_api import RecClient

NID = re.compile(r'/berita/(N\d+)')


def feed_nids(client) -> list[str]:
    return NID.findall(client.get("/").text)


def _uid(client) -> int:
    return int(client.app.state.store.get_user_by_email("budi@example.com")["id"])


def test_no_history_shows_popular_label(client, register):
    register()
    body = client.get("/").text
    assert "Berita populer" in body                    # TEST-AC-049/051
    nids = NID.findall(body)
    assert 1 <= len(nids) <= 10                        # TEST-AC-040
    assert len(set(nids)) == len(nids)                 # TEST-AC-048


def test_history_switches_to_cold_and_filters(client, register):
    register()
    first = feed_nids(client)
    for nid in first[:3]:
        client.get(f"/berita/{nid}")

    body = client.get("/").text
    assert "Rekomendasi dari riwayat bacaanmu" in body  # TEST-AC-050/051
    second = NID.findall(body)
    assert not (set(second) & set(first[:3]))           # TEST-AC-047
    assert len(set(second)) == len(second)              # TEST-AC-048


def test_feed_never_exceeds_ten(client, register):
    register()
    for nid in feed_nids(client)[:5]:
        client.get(f"/berita/{nid}")
    assert len(NID.findall(client.get("/").text)) <= 10  # TEST-AC-040


def test_history_payload_is_capped(client, register):
    """At most WEB_HISTORY_LIMIT unique nids are sent to the API."""
    register()
    store = client.app.state.store
    for nid in [f"N{i}" for i in range(80)]:
        store.add_view(_uid(client), nid, "direct")
    nids = store.history_nids(_uid(client), 50)
    assert len(nids) == 50                              # TEST-AC-023
    assert len(set(nids)) == 50


def test_full_history_filter_set_covers_all_rows(client, register):
    """The filter uses every row, not just the 50 that were sent."""
    register()
    store = client.app.state.store
    for nid in [f"N{i}" for i in range(80)]:
        store.add_view(_uid(client), nid, "direct")
    assert len(store.all_history_nids(_uid(client))) == 80
    assert len(store.history_nids(_uid(client), 50)) == 50


def test_payload_has_exactly_one_selector(client, register, monkeypatch):
    """Assert on the real request bodies the client emits."""
    register()
    for nid in feed_nids(client)[:2]:
        client.get(f"/berita/{nid}")

    sent: list[dict] = []
    original = RecClient.recommend

    async def spy(self, payload):
        sent.append(dict(payload))
        return await original(self, payload)

    monkeypatch.setattr(RecClient, "recommend", spy)
    client.get("/")

    assert sent, "no /recommend call was made"
    for payload in sent:
        assert ("user_id" in payload) != ("history" in payload)   # TEST-AC-045
        assert "alpha" not in payload                            # TEST-AC-046
        assert 1 <= payload["top_k"] <= 100                      # TEST-AC-046/I6
        assert payload["top_k"] == 30                            # TEST-AC-021/022


def test_popular_path_makes_no_model_call(client, register, monkeypatch):
    """No history -> popular feed, which must not call /recommend."""
    register()
    calls: list[dict] = []
    original = RecClient.recommend

    async def spy(self, payload):
        calls.append(dict(payload))
        return await original(self, payload)

    monkeypatch.setattr(RecClient, "recommend", spy)
    body = client.get("/").text
    assert "Berita populer" in body
    assert calls == []                                   # TEST-AC-049


def test_order_matches_api_response(client, register, monkeypatch):
    """The feed renders API order, minus already-read nids (TEST-AC-042)."""
    register()
    store = client.app.state.store
    store.add_view(_uid(client), "N44146", "feed")   # one pre-read item

    captured: list[list[str]] = []
    original = RecClient.recommend

    async def spy(self, payload):
        body = await original(self, payload)
        captured.append([a["nid"] for a in body["recommendations"]])
        return body

    monkeypatch.setattr(RecClient, "recommend", spy)
    rendered = feed_nids(client)

    assert captured
    expected = [n for n in captured[-1] if n != "N44146"][:10]
    assert rendered == expected


def test_persona_404_falls_back_to_history(client, register):
    """Invalid persona id must not surface a raw error (TEST-AC-092)."""
    register()
    store = client.app.state.store
    uid = _uid(client)
    with store.connect() as conn:
        conn.execute("UPDATE users SET persona_user_id = 'U000_nope' WHERE id = ?", (uid,))
    store.add_view(uid, "N44146", "feed")

    r = client.get("/")
    assert r.status_code == 200
    assert "Rekomendasi dari riwayat bacaanmu" in r.text
    assert "Traceback" not in r.text
