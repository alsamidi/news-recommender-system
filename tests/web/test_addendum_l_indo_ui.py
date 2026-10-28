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


def test_no_author_and_source_link_only_from_data(client, register):
    """TEST-AC-222 / TEST-AC-273 (amended v1.3).

    `Sumber:`/`Tanggal:` stay mandatory; the author is still forbidden. The
    portal-link ban is narrowed rather than dropped: exactly one link is
    allowed, it must sit after the body, and its host must match the article's
    own `source` — a fabricated or mismatched link still fails.
    """
    import pandas as pd

    catalog = pd.read_parquet(REPO / "data/processed/indo/catalog.parquet",
                              columns=["nid", "source"])
    source_of = dict(zip(catalog["nid"], catalog["source"]))

    for nid in _first_nids(client, register, 2):
        body = client.get(f"/berita/{nid}").text
        assert "Sumber: " in body
        assert "Tanggal: " in body
        assert "Penulis" not in body
        assert "Penerbit" not in body

        links = re.findall(r'<a href="(https?://[^"]+)"', body)
        assert len(links) == 1, links
        host = links[0].split("/")[2]
        assert source_of[nid] in host, (nid, host, source_of[nid])
        # The link must come after the body block, never inside it.
        assert body.index("article-body") < body.index(links[0])


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


def test_body_starts_without_dateline_comma(client, register):
    """TEST-AC-268 / v1.3 #2: display-only cleanup of the leftover dateline comma.

    34.4% of bodies (90.7% of Tempo rows) start with ", ". It is stripped when
    rendering, never in the corpus — the lock hash and every gate number stay
    valid.
    """
    for nid in _first_nids(client, register, 4):
        body = client.get(f"/berita/{nid}").text
        m = re.search(r'<div class="article-body[^"]*">(.*?)</div>', body, re.S)
        if not m:
            continue
        first = m.group(1).lstrip()[:3]
        assert not first.startswith(","), (nid, first)


def test_article_body_is_justified(client, register):
    """TEST-AC-269 / v1.3 #3: justified body with a first-line indent."""
    from pathlib import Path

    css = (REPO / "src/web/static/app.css").read_text()
    block = re.search(r"\.article-body \{([^}]*)\}", css)
    assert block, "article-body block missing"
    assert "text-align: justify" in block.group(1)
    assert "text-indent:" in block.group(1)


def test_history_rows_share_one_height(client, register):
    """TEST-AC-270: uniform row height, measured on the rendered markup.

    The structural invariant (four grid children) is asserted elsewhere; this
    checks that the meta cell always occupies two lines, which is what makes
    rows visually uniform. A browser measurement is in the goal's verification
    step; this is the cheap structural proxy that runs in CI.
    """
    register()
    nids = _first_nids(client, register, 3)
    for nid in nids:
        client.get(f"/berita/{nid}")

    body = client.get("/histori").text
    rows = re.findall(r'<li class="history-row">(.*?)</li>', body, re.S)
    assert len(rows) >= 2
    shapes = []
    for row in rows:
        shapes.append(row.count('class="history-meta-line"'))
    # Every row carries the same meta-line count: 2 when source/date exist.
    assert len(set(shapes)) == 1, shapes


# ---------------------------------------------------------------------------
# D31 — detail-page reading column (TEST-AC-276/277/278)
# ---------------------------------------------------------------------------

def _detail_html(client, register) -> str:
    """One rendered detail page for the first article in the feed."""
    nid = _first_nids(client, register, 1)[0]
    return client.get(f"/berita/{nid}").text


def test_detail_content_shares_one_reading_column(client, register):
    """TEST-AC-276 (D31): the reading surface is one column, not four widths.

    Breadcrumb, headline, meta line, body and the portal link must all sit
    inside `.article-column`, and the related grid must sit outside it — it is
    a browsing surface and stays full width. Asserted structurally (nesting),
    because the visual consequence — one shared left edge — only exists if the
    nesting is right.
    """
    body = _detail_html(client, register)
    column = re.search(r'<div class="article-column">(.*?)\n  </div>\n</article>',
                       body, re.S)
    assert column, "no .article-column wrapping the detail content"
    inner = column.group(1)

    for marker in ('class="breadcrumb"', 'class="article-headline"',
                   'class="meta-row"', 'class="article-body',
                   'class="article-source"'):
        assert marker in inner, f"{marker} is outside the reading column"

    # The related grid is rendered after the column closes.
    assert 'class="card-grid"' in body
    assert body.index('class="card-grid"') > body.index('class="article-column"')


def test_detail_headline_is_thirty_six_pixels(client, register):
    """TEST-AC-277 (D31): the detail headline came down from 40px to 36px."""
    css = (REPO / "src/web/static/app.css").read_text()
    block = re.search(r"\.article-headline \{([^}]*)\}", css).group(1)
    assert "font-size: 36px" in block
    assert "40px" not in block
    # Still a local override: the token scale itself is untouched.
    tokens = (REPO / "src/web/static/tokens.css").read_text()
    assert "--typography-display" not in tokens


def test_measure_lives_on_the_column_only(client, register):
    """TEST-AC-278 (D31): one measure, owned by the column.

    Two caps (column + body) is how the headline width and the paragraph width
    drift apart, so the body must not carry its own `max-width`.
    """
    css = (REPO / "src/web/static/app.css").read_text()
    column = re.search(r"\.article-column \{([^}]*)\}", css)
    assert column, "article-column block missing"
    assert "max-width: var(--layout-reading)" in column.group(1)
    assert "margin: 0 auto" in column.group(1)

    body_block = re.search(r"\.article-body \{([^}]*)\}", css).group(1)
    assert re.search(r"max-width:\s*none", body_block), body_block
    assert "70ch" not in body_block

