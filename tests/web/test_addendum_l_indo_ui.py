"""PRD v1.1 addendum §L acceptance criteria (TEST-AC-060/065/081/083/085/086/221/222).

These pin the *corpus transition* rules that the MIND-era suite encoded
backwards: the active corpus really has `source` and a publication date, so
the UI must show them, and it must still never invent an author, a portal
link, an image, or an article count.

Numbering note: the repo carries two AC namespaces (`PRD-AC-xx` in the PRD and
`TEST-AC-xxx` in ACCEPTANCE_CRITERIA.md). This module cites the TEST-AC ids
from the addendum table so the mapping stays mechanical.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "src" / "web" / "templates"

NID = re.compile(r"/berita/([NI][0-9a-zA-Z]+)")
DATE = re.compile(r"\b\d{1,2} (Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des) \d{4}\b")


def _first_nids(client, register, n: int = 5) -> list[str]:
    register()
    body = client.get("/").text
    out: list[str] = []
    for nid in NID.findall(body):
        if nid not in out:
            out.append(nid)
        if len(out) == n:
            break
    assert out, "feed rendered no articles"
    return out


def test_detail_shows_full_content_source_and_date(client, register):
    """TEST-AC-060 (addendum §L): title, category, source, date, full content.

    The corpus has no abstract, so the body shown is `content`. A detail page
    that only shows a title would silently drop the article.
    """
    for nid in _first_nids(client, register, 3):
        body = client.get(f"/berita/{nid}").text
        assert "article-headline" in body
        assert "Sumber: " in body
        assert "Tanggal: " in body
        assert DATE.search(body), "no rendered publication date"
        assert 'class="article-body' in body
        # The body is the catalogue content, not processed_text.
        assert "processed" not in body.lower()


def test_short_or_empty_content_renders_cleanly(client, register):
    """TEST-AC-065 (addendum §L): no placeholder paragraph, no `None`.

    PRD §16: when the body is empty the page shows title + meta only. A
    substitute sentence would be copy the data cannot support.
    """
    nid = _first_nids(client, register, 1)[0]
    body = client.get(f"/berita/{nid}").text
    assert "None" not in body
    assert "Ringkasan tidak tersedia" not in body
    assert "Tidak ada konten" not in body


def test_card_meta_is_category_source_and_date_only(client, register):
    """TEST-AC-221 (addendum §L): meta = category + source + date."""
    register()
    body = client.get("/").text
    card = re.search(r'<a class="card".*?</a>', body, re.S).group(0)
    assert 'class="card-category"' in card
    assert "Sumber: " in card
    assert DATE.search(card)
    assert "card-abstract" not in card


def test_no_author_no_portal_link_but_source_and_date_labelled(client, register):
    """TEST-AC-222 (addendum §L, partly reversed).

    `Sumber:`/`Tanggal:` are mandatory when the corpus carries the value;
    author and portal links remain forbidden.
    """
    for nid in _first_nids(client, register, 2):
        body = client.get(f"/berita/{nid}").text
        assert "Sumber: " in body
        assert "Tanggal: " in body
        assert "Penulis" not in body
        assert "Penerbit" not in body
        assert 'href="http' not in body
        for domain in ("detik.com", "tempo.co", "kompas.com"):
            assert domain not in body


def test_rendered_source_matches_catalog(client, register):
    """TEST-AC-081 (addendum §L): the source label is real, not invented."""
    import pandas as pd

    catalog = pd.read_parquet(REPO / "data/processed/indo/catalog.parquet",
                              columns=["nid", "source"])
    by_nid = dict(zip(catalog["nid"], catalog["source"]))
    for nid in _first_nids(client, register, 3):
        body = client.get(f"/berita/{nid}").text
        expected = by_nid[nid].capitalize()
        assert f"Sumber: {expected}" in body, (nid, expected)


def test_rendered_date_matches_catalog(client, register):
    """TEST-AC-083 (addendum §L): the rendered date is the real one."""
    import pandas as pd

    catalog = pd.read_parquet(REPO / "data/processed/indo/catalog.parquet",
                              columns=["nid", "published_at"])
    by_nid = dict(zip(catalog["nid"], catalog["published_at"]))
    from web.services.catalog_meta import format_published_at

    for nid in _first_nids(client, register, 3):
        body = client.get(f"/berita/{nid}").text
        expected = format_published_at(by_nid[nid])
        assert f"Tanggal: {expected}" in body, (nid, expected)


def test_rendered_categories_are_served_catalog_values(client, register):
    """TEST-AC-085 (addendum §L): displayed categories ∈ served catalog."""
    import pandas as pd

    catalog = pd.read_parquet(REPO / "data/processed/indo/catalog.parquet",
                              columns=["category"])
    served = set(catalog["category"].unique())

    register()
    body = client.get("/").text
    rendered = re.findall(r'class="card-category">([^<]+)<', body)
    assert rendered
    assert set(rendered) <= served


def test_no_hardcoded_article_count_anywhere(client, register):
    """TEST-AC-086 (addendum §L): counts come from the lock, never code.

    The lock records 67,381 unique articles and 17,584 effective items. A
    template or route that prints either as static copy would go stale the
    moment the corpus is re-locked, so no such literal may exist.
    """
    register()
    pages = [client.get("/").text, client.get("/histori").text]
    for body in pages:
        assert "67.381" not in body
        assert "67381" not in body
        assert "17.584" not in body
        assert "17584" not in body
    for path in list(TEMPLATES.glob("*.html")) + [
            REPO / "src" / "web" / "routes" / "feed.py"]:
        text = path.read_text()
        for literal in ("67381", "17584", "93698", "93.698"):
            assert literal not in text, (path.name, literal)


def test_history_row_keeps_four_grid_cells(client, register):
    """TEST-AC-257: every history row has the same column geometry.

    `.history-row` is a four-column grid (`minmax(0,1fr) 120px 210px 220px`).
    A row with five or six children spills the extras into an implicit second
    row, which pushes "Dibaca ..." and the reader counts down and makes the
    columns disagree between rows. Category + source + date therefore share
    one cell.
    """
    from bs4 import BeautifulSoup

    register()
    nids = _first_nids(client, register, 2)
    for nid in nids:
        client.get(f"/berita/{nid}")

    soup = BeautifulSoup(client.get("/histori").text, "html.parser")
    rows = soup.select("li.history-row")
    assert rows, "history rendered no rows"
    for row in rows:
        children = [c for c in row.children if getattr(c, "name", None)]
        assert len(children) == 4, [c.name for c in children]
        assert children[0].name == "a"                    # title link
        assert "history-cat" in (children[1].get("class") or [])
        assert children[2].name == "time"
        assert "history-readers" in (children[3].get("class") or [])
        # Source and date live inside the category cell, not as new columns.
        assert "Sumber: " in children[1].get_text()
