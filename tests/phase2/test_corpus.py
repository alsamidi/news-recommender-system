import pandas as pd
import pytest

from src.phase2.corpus import dedupe


def _rows(links, judul, content, waktu):
    return pd.DataFrame({
        "Judul": judul,
        "Waktu": waktu,
        "Link": links,
        "Content": content,
    })


def test_identical_duplicates_collapse_to_one():
    df = _rows(
        links=["https://a.co/1", "https://a.co/1", "https://b.co/2",
               "https://b.co/2", "https://b.co/2"],
        judul=["T1", "T1", "T2", "T2", "T2"],
        content=["C1", "C1", "C2", "C2", "C2"],
        waktu=["2 September 2025", "1 September 2025",
               "10 Agu 2025", "9 Agu 2025", "8 Agu 2025"],
    )
    out = dedupe(df)
    assert len(out) == 2
    assert set(out["Link"]) == {"https://a.co/1", "https://b.co/2"}
    # deterministic keep="first" after sort by (Link, Waktu); the sorted
    # order makes row selection reproducible across runs.
    assert out.iloc[0]["Link"] == "https://a.co/1"


def test_differing_content_raises():
    df = _rows(
        links=["https://a.co/1", "https://a.co/1"],
        judul=["T1", "T1"],
        content=["C1", "C1-different"],
        waktu=["1 September 2025", "2 September 2025"],
    )
    with pytest.raises(ValueError, match="differing content"):
        dedupe(df)


def test_differing_judul_raises():
    df = _rows(
        links=["https://a.co/1", "https://a.co/1"],
        judul=["T1", "T1-revised"],
        content=["C1", "C1"],
        waktu=["1 September 2025", "1 September 2025"],
    )
    with pytest.raises(ValueError, match="differing content"):
        dedupe(df)


def test_nan_vs_nan_counts_identical():
    # measured real case: infographic pages scraped twice with empty Content
    df = _rows(
        links=["https://a.co/1", "https://a.co/1"],
        judul=[None, None],
        content=[None, None],
        waktu=["1 September 2025", "1 September 2025"],
    )
    out = dedupe(df)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# Task 4: URL-section categories
# ---------------------------------------------------------------------------

from urllib.parse import urlparse

import pandas as pd

from src.phase2.corpus import SECTION_TO_LABEL, add_categories, build_category_map, extract_section


def test_extract_section_tempo():
    assert extract_section(
        "https://www.tempo.co/politik/some-title-1173464", "tempo") == "politik"
    assert extract_section(
        "https://tempo.co/ekonomi/x-1", "tempo") == "ekonomi"


def test_extract_section_detik():
    assert extract_section(
        "https://news.detik.com/berita/d-7947358/x", "detik") == "berita"
    assert extract_section(
        "https://news.detik.com/dw/d-7571144/y", "detik") == "dw"


def test_extract_section_kompas_subdomain():
    # canonical read URLs carry no section in the path; subdomain does
    assert extract_section(
        "https://nasional.kompas.com/read/2024/08/02/17263401/x", "kompas") == "nasional"
    assert extract_section(
        "https://megapolitan.kompas.com/read/2025/04/15/17400331/y", "kompas") == "megapolitan"


def test_extract_section_rejects_garbage():
    with pytest.raises(ValueError):
        extract_section("", "tempo")
    with pytest.raises(ValueError):
        extract_section("https://cnn.com/x", "tempo")
    with pytest.raises(ValueError):
        extract_section("https://www.kompas.com/read/x", "kompas")  # no subdomain
    with pytest.raises(ValueError):
        extract_section("https://nasional.kompas.com/read/x", "hackernews")


def test_full_csv_category_coverage_100pct():
    df = pd.read_csv("data/raw/final_merge_dataset.csv", usecols=["Link", "source"])
    labeled = add_categories(df)
    assert labeled["category"].notna().all()
    assert (labeled["category"].astype(str).str.len() > 0).all()
    # measured inventory: every extracted section must be in the explicit map
    sections = [extract_section(u, s) for u, s in zip(df["Link"], df["source"])]
    assert set(sections) <= set(SECTION_TO_LABEL)
    per_src = build_category_map(df)
    assert set(per_src) == {"kompas", "tempo", "detik"}
