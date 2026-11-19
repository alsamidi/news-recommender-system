import pytest

from src.phase2.textproc import (
    MAX_TOKEN_LEN,
    IndoPreprocessor,
    clean_text,
    load_stopwords,
)


def test_clean_text_v1_rules():
    raw = "  Harga BERAS Naik 12% di JAKARTA!! https://x.co/a @user #tag  "
    out = clean_text(raw)
    assert out == "harga beras naik di jakarta"


def test_clean_text_nonstr():
    assert clean_text(None) == ""
    assert clean_text("") == ""


def test_stem_and_mask_pipeline():
    prep = IndoPreprocessor()
    # "membeli" -> "beli" (Sastrawi), stopwords drop "di"/"dan"
    out = prep.process("Dia membeli beras di pasar dan menjualnya")
    toks = out.split()
    assert "beli" in toks or "membeli" in toks
    assert "di" not in toks and "dan" not in toks
    assert all(2 <= len(t) <= MAX_TOKEN_LEN for t in toks)


def test_stem_cache_reuse():
    prep = IndoPreprocessor()
    a = prep.process("makanan enak")
    n = len(prep._cache)
    b = prep.process("makanan enak")
    assert a == b and len(prep._cache) == n  # same stems, no growth


def test_stem_timeout_falls_back_to_word(monkeypatch):
    prep = IndoPreprocessor()
    from src.phase2.textproc import _StemTimeout

    class Slow:
        def stem(self, word):
            raise _StemTimeout()

    prep.stemmer = Slow()
    out = prep.process("kompleks")
    assert "kompleks" in out  # timed-out token survives unchanged


def test_stopwords_loaded_from_config():
    sw = load_stopwords()
    assert {"yang", "dan", "di"} <= sw
    assert len(sw) > 40


def test_assemble_uses_injected_cache_only():
    prep = IndoPreprocessor()
    prep.use_cache({"makan": "makan", "beras": "beras"})
    assert prep.assemble("makan beras xyz") == "makan beras xyz"
    assert prep.process("makan beras") == "makan beras"
