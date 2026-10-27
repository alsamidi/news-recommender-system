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


# ---------------------------------------------------------------------------
# Task 5: boilerplate stripping
# ---------------------------------------------------------------------------

from src.phase2.corpus import strip_boilerplate, strip_corpus


def test_strip_tempo_banners():
    raw = ("Baca berita dengan sedikit iklan,  klik di sini  TEMPO.CO, Jakarta - "
           "Isi berita.  Scroll ke bawah untuk melanjutkan membaca   Baca berita "
           "dengan sedikit iklan,  klik di sini  Isi lanjutan. Pilihan Editor: X")
    out = strip_boilerplate(raw, "tempo")
    assert "Baca berita" not in out and "klik di sini" not in out
    assert "Scroll ke bawah" not in out
    assert "Isi berita." in out and "Isi lanjutan." in out


def test_strip_detik_gambas_and_linkblog_tail():
    raw = ("Isi berita utama di sini.  Lihat juga Video Sosok X  [Gambas:Video 20detik]  "
           "Isi akhir.   Simak juga, Video: Y [Gambas:Photo 20detik]")
    out = strip_boilerplate(raw, "detik")
    assert "[Gambas:" not in out
    assert "Simak juga" not in out and "Lihat juga" not in out
    assert "Isi berita utama di sini." in out and "Isi akhir." in out


def test_detik_linkblog_midbody_without_gambas_is_kept():
    # measured corner case (1 article, 3 dup rows): fragment mid-body, no
    # placeholder — must NOT eat the following body text
    raw = ("Isi berita utama di sini.  Tonton juga video \"Cerita X\" di sini:     "
           "Masih di Jalan TB Simatupang, jalanan macet total.")
    out = strip_boilerplate(raw, "detik")
    assert "Masih di Jalan TB Simatupang" in out


def test_strip_kompas_dateline_byline():
    raw = (" JAKARTA, KOMPAS.com -\xa0Isi berita yang panjang hingga akhir paragraf. "
           "(Reporter: Sinta | Editor: Budi)")
    out = strip_boilerplate(raw, "kompas")
    assert "KOMPAS.com" not in out and "JAKARTA" not in out
    assert "Reporter:" not in out
    assert out.startswith("Isi berita")


def test_strip_unknown_source_raises():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        strip_boilerplate("x", "cnn")


def test_strip_corpus_keeps_short_and_median_gt_1000():
    df = pd.read_csv("data/raw/final_merge_dataset.csv",
                     usecols=["Content", "source"]).sample(3000, random_state=3)
    out = strip_corpus(df)
    assert len(out) == len(df)  # no row dropped, short contents kept
    lens = out["Content"].str.len()
    assert (lens > 0).all()
    assert lens.median() > 1_000
    short_before = (df["Content"].fillna("").astype(str).str.len() < 200).sum()
    if short_before:
        assert (out["Content"].str.len() < 200).sum() >= 1  # short kept, not dropped


def test_full_csv_strip_median_and_length_gain():
    df = pd.read_csv("data/raw/final_merge_dataset.csv",
                     usecols=["Content", "source"])
    out = strip_corpus(df)
    raw_med = df["Content"].fillna("").astype(str).str.len().median()
    strip_med = out["Content"].str.len().median()
    print(f"median raw={raw_med:.0f} stripped={strip_med:.0f}")
    assert strip_med > 1_000 and strip_med <= raw_med
