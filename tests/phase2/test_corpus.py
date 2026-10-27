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
