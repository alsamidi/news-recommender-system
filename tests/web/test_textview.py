"""Display-layer helpers: dateline cleanup and portal-link reconstruction.

Both are presentation-only by design: the corpus is frozen, so the comma that
precedes 34.4% of bodies is stripped at render time, and the portal URL is
derived from `nid = sha1(Link)` instead of adding a column to the catalogue
(which would invalidate its recorded sha256).
"""
from __future__ import annotations

import hashlib

import pandas as pd

from web.services.textview import build_source_urls, strip_leading_dateline


# --- strip_leading_dateline -------------------------------------------------

def test_strips_the_measured_dateline_comma():
    """The real shape: `", TEMPO.CO, Jakarta - ..."` (90.7% of Tempo rows)."""
    assert strip_leading_dateline(
        ", TEMPO.CO, Jakarta - Dosen UNJ Ubedilah Badrun kembali melapor"
    ) == "TEMPO.CO, Jakarta - Dosen UNJ Ubedilah Badrun kembali melapor"


def test_strips_repeated_and_spaced_punctuation():
    assert strip_leading_dateline(", , TEMPO.CO - isi") == "TEMPO.CO - isi"
    assert strip_leading_dateline("  ,  isi") == "isi"
    assert strip_leading_dateline("; isi") == "isi"


def test_leaves_clean_bodies_untouched():
    """detik/kompas rows start with a word; nothing may change for them."""
    for text in ("JAKARTA, KOMPAS.com - Presiden", "DALAM sejarah modern"):
        assert strip_leading_dateline(text) == text


def test_keeps_legitimate_opening_punctuation():
    """Only dateline junk is removed: quotes and brackets are content."""
    assert strip_leading_dateline('"Kutipan" pembuka') == '"Kutipan" pembuka'
    assert strip_leading_dateline("(Foto: istimewa)") == "(Foto: istimewa)"


def test_handles_empty_and_none():
    assert strip_leading_dateline("") == ""
    assert strip_leading_dateline(None) is None


def test_does_not_touch_inner_punctuation():
    text = "Dia berkata, \"halo\", lalu pergi"
    assert strip_leading_dateline(text) == text


# --- build_source_urls ------------------------------------------------------

def _nid(link: str) -> str:
    return "I" + hashlib.sha1(link.encode()).hexdigest()[:10]


def test_maps_nid_back_to_its_link(tmp_path):
    """`nid` is defined as sha1(Link)[:10], so the mapping is exact."""
    link = "https://news.detik.com/berita/d-1/contoh"
    csv = tmp_path / "raw.csv"
    csv.write_text(f"Link,source\n{link},detik\n")
    got = build_source_urls({_nid(link)}, str(csv), None)
    assert got == {_nid(link): link}


def test_only_catalogue_nids_are_returned(tmp_path):
    """Rows outside the catalogue must not leak into the map."""
    inside = "https://www.tempo.co/a"
    outside = "https://www.tempo.co/b"
    csv = tmp_path / "raw.csv"
    csv.write_text(f"Link,source\n{inside},tempo\n{outside},tempo\n")
    got = build_source_urls({_nid(inside)}, str(csv), None)
    assert set(got) == {_nid(inside)}


def test_missing_csv_yields_no_links_instead_of_inventing_one(tmp_path):
    """No data means no link: the detail page falls back to the source name."""
    assert build_source_urls({_nid("https://x/y")}, str(tmp_path / "nope.csv"), None) == {}


def test_blank_links_are_skipped(tmp_path):
    csv = tmp_path / "raw.csv"
    csv.write_text("Link,source\n,detik\n")
    assert build_source_urls({_nid("")}, str(csv), None) == {}

def test_derived_parquet_is_preferred_over_the_raw_csv(tmp_path):
    """The image ships the 3.2 MB parquet, not the 207 MB CSV."""
    link = "https://www.tempo.co/politik/contoh-1"
    pq = tmp_path / "links.parquet"
    pd.DataFrame({"nid": [_nid(link)], "url": [link]}).to_parquet(pq, index=False)
    got = build_source_urls({_nid(link)}, str(tmp_path / "absent.csv"), str(pq))
    assert got == {_nid(link): link}


def test_parquet_rows_outside_the_catalogue_are_filtered(tmp_path):
    inside = "https://www.tempo.co/a"
    outside = "https://www.tempo.co/b"
    pq = tmp_path / "links.parquet"
    pd.DataFrame({"nid": [_nid(inside), _nid(outside)],
                  "url": [inside, outside]}).to_parquet(pq, index=False)
    got = build_source_urls({_nid(inside)}, str(tmp_path / "absent.csv"), str(pq))
    assert set(got) == {_nid(inside)}


def test_missing_parquet_falls_back_to_the_csv(tmp_path):
    """Checkouts without the derived file must keep working exactly as before."""
    link = "https://news.detik.com/berita/d-2/contoh"
    csv = tmp_path / "raw.csv"
    csv.write_text(f"Link,source\n{link},detik\n")
    got = build_source_urls({_nid(link)}, str(csv), str(tmp_path / "absent.parquet"))
    assert got == {_nid(link): link}
