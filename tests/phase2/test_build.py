import hashlib

import pandas as pd
import pytest

from src.phase2 import build_corpus_indo as b
from src.phase2.textproc import IndoPreprocessor


class FastPreprocessor(IndoPreprocessor):
    """Deterministic stub: no Sastrawi dictionary load, no real stemming.

    Keeps per-commit pytest fast; real Sastrawi coverage lives in
    test_textproc.py (unit) and in the actual 2k-slice/full build runs.
    """

    def __init__(self):
        self.stemmer = type("S", (), {"stem": staticmethod(lambda w: w)})()
        self.stopword_remover = type(
            "R", (), {"remove": staticmethod(lambda t: t)})()
        from src.phase2.textproc import load_stopwords, STOPWORDS_PATH
        self.custom_stopwords = load_stopwords(STOPWORDS_PATH)
        self._cache = {}


@pytest.fixture(autouse=True)
def _fast_prep(monkeypatch):
    # Inline build path (workers=1, <1000 rows) only; keeps pytest fast.
    monkeypatch.setattr(b, "IndoPreprocessor", FastPreprocessor)


def _fake_raw(n_links=3, dup=1):
    links = [f"https://www.tempo.co/politik/art-{i}" for i in range(n_links)]
    rows = {
        "Judul": [f"Judul {i}" for i in range(n_links)],
        "Waktu": ["16 Juli 2025 | 10.17 WIB"] * n_links,
        "Link": links,
        "Content": ["isi berita " * 100] * n_links,
        "source": ["tempo"] * n_links,
    }
    return pd.DataFrame(rows)


def test_make_nid_scheme():
    url = "https://www.tempo.co/politik/x-1"
    expect = "I" + hashlib.sha1(url.encode()).hexdigest()[:10]
    assert b.make_nid(url) == expect
    assert b.make_nid(url).startswith("I") and len(b.make_nid(url)) == 11


def test_nid_collision_is_hard_failure(monkeypatch):
    monkeypatch.setattr(b, "load_raw", lambda slice_n=None: _fake_raw(2))
    monkeypatch.setattr(b, "make_nid", lambda u: "ICOLLIDE")  # force collision
    with pytest.raises(ValueError, match="nid collision"):
        b.build(slice_n=None, workers=1)


def test_unique_count_lock_assert(monkeypatch):
    monkeypatch.setattr(b, "load_raw", lambda slice_n=None: _fake_raw(1))
    with pytest.raises(ValueError, match="!= lock"):
        b.build(slice_n=None, workers=1)


def test_slice_build_contract(monkeypatch, tmp_path):
    raw = b.load_raw(slice_n=80)  # single real CSV read for this test
    monkeypatch.setattr(b, "load_raw", lambda slice_n=None: raw)
    cat, summary = b.build(slice_n=50, workers=1)
    assert list(cat.columns) == ["nid", "title", "content", "processed_text",
                                 "category", "source", "published_at", "split"]
    assert len(cat) > 0 and cat["nid"].is_unique
    assert (cat["split"] == "unsplit").all()
    assert cat["published_at"].dt.tz is not None
    assert cat["processed_text"].str.len().gt(0).mean() > 0.95
    assert set(summary) >= {"unique_rows", "per_source", "category_counts",
                            "median_content_chars", "vocab_unique"}
    out = b.write_outputs(cat, summary, tmp_path / "c.parquet",
                          tmp_path / "s.json")
    import json
    s = json.loads((tmp_path / "s.json").read_text())
    assert s["catalog_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert s["unique_rows"] == len(cat)
