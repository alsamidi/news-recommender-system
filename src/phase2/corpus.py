"""Corpus assembly: dedupe, URL-section categories, boilerplate stripping."""
from urllib.parse import urlparse

import pandas as pd


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate URLs deterministically.

    Sorts by (Link, Waktu) and keeps the first row per URL. Hard-fails with
    ValueError when any URL group carries differing Judul or Content — the
    measured vetting says duplicates are 100% identical re-scrapes; a
    violation means the assumption is broken, not something to heal silently.
    """
    key_cols = ["Judul", "Content"]
    inconsistent = []
    for link, grp in df.groupby("Link", sort=False):
        # nunique(dropna=False): NaN vs NaN counts as identical (pandas element
        # == would call NaN != NaN); string vs NaN still fails, as it should.
        for col in key_cols:
            if grp[col].nunique(dropna=False) > 1:
                inconsistent.append((link, col))
                break
    if inconsistent:
        raise ValueError(
            f"duplicate URL groups with differing content: {inconsistent[:5]}"
        )
    out = df.sort_values(["Link", "Waktu"], kind="mergesort")
    return out.drop_duplicates(subset="Link", keep="first").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Task 4: URL-section category derivation
# ---------------------------------------------------------------------------

def extract_section(url: str, source: str) -> str:
    """Extract the raw URL section for one article.

    Measured rules (probe on the full CSV, 2026-10-27):
      tempo : first path segment after tempo.co/ (leading www stripped);
              e.g. https://www.tempo.co/politik/... -> "politik"
      detik : channel path segment on news.detik.com, e.g.
              https://news.detik.com/berita/d-... -> "berita"
      kompas: subdomain before .kompas.com — canonical read URLs do not embed
              the section; the subdomain carries it
              (nasional/megapolitan/regional/internasional measured).
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"empty URL for section extraction (source={source})")
    if source == "tempo":
        host = urlparse(url).netloc
        if not host.endswith("tempo.co"):
            raise ValueError(f"tempo row with foreign host: {url!r}")
        segs = [s for s in urlparse(url).path.split("/") if s]
        if not segs:
            raise ValueError(f"tempo URL without path section: {url!r}")
        return segs[0].lower()
    if source == "detik":
        host = urlparse(url).netloc
        if not host.endswith("detik.com"):
            raise ValueError(f"detik row with foreign host: {url!r}")
        segs = [s for s in urlparse(url).path.split("/") if s]
        # measured shape: /<channel>/d-<id>/...; detiktv/infografis keep d-id too
        if not segs:
            raise ValueError(f"detik URL without path channel: {url!r}")
        return segs[0].lower()
    if source == "kompas":
        host = urlparse(url).netloc
        if not host.endswith("kompas.com"):
            raise ValueError(f"kompas row with foreign host: {url!r}")
        sub = host[: -len(".kompas.com")].lower()
        if not sub or sub == "www":
            raise ValueError(f"kompas URL without section subdomain: {url!r}")
        return sub
    raise ValueError(f"unknown source: {source!r}")


# Section (raw URL segment) -> final category label. Built from the measured
# full-CSV section inventory; unknown section = hard build failure, never a
# silent fallback.
SECTION_TO_LABEL = {
    # --- tempo ---
    "politik": "Politik",
    "hukum": "Hukum",
    "ekonomi": "Ekonomi",
    "internasional": "Internasional",
    "olahraga": "Olahraga",
    "sepakbola": "Olahraga",
    "hno": "Olahraga",
    "bola": "Olahraga",
    "hiburan": "Hiburan",
    "gaya-hidup": "Hiburan",
    "musik": "Hiburan",
    "seleb": "Hiburan",
    "teroka": "Teroka",
    "sains": "Tekno-Sains",
    "digital": "Tekno-Sains",
    "tekno": "Tekno-Sains",
    "lingkungan": "Lingkungan",
    "kolom": "Kolom",
    "cekfakta": "Cek Fakta",
    "info-tempo": "Info Tempo",
    "foto": "Multimedia",
    "video": "Multimedia",
    "infografik": "Multimedia",
    "arsip": "Info Tempo",
    "newsletter": "Info Tempo",
    "data": "Info Tempo",
    "prelude": "Info Tempo",
    "tokoh": "Kolom",
    "wawancara": "Kolom",
    "investigasi": "Investigasi",
    "otomotif": "Otomotif",
    # same section, both spellings measured
    "ramadan": "Ramadan",
    "ramadhan": "Ramadan",
    # --- detik ---
    "berita": "Berita",
    "pilkada": "Pemilu",
    "pemilu": "Pemilu",
    "dw": "Internasional",
    "bbc-world": "Internasional",
    "abc-australia": "Internasional",
    "internasional-utama": "Internasional",
    "kolom": "Kolom",
    "detiktv": "Multimedia",
    "infografis": "Multimedia",
    "adv-nhl-detikcom": "Bersponsor",
    "bangun-indonesia": "Bersponsor",
    "melindungi-tuah-marwah": "Bersponsor",
    # --- kompas ---
    "nasional": "Berita",
    "megapolitan": "Berita",
    "regional": "Berita",
}


def build_category_map(df: pd.DataFrame) -> dict:
    """Map sections to labels and return {source -> {section -> label}}.

    Hard-fails on any row whose section is missing from SECTION_TO_LABEL —
    measured coverage is 100%; a miss means the corpus drifted.
    """
    sections = pd.Series(
        [extract_section(u, s) for u, s in zip(df["Link"], df["source"])],
        name="section",
    )
    unknown = sorted(set(sections) - set(SECTION_TO_LABEL))
    if unknown:
        raise ValueError(
            f"unknown URL sections ({len(unknown)}): {unknown[:20]}"
        )
    per_source: dict = {}
    for src, grp in pd.DataFrame({"source": df["source"], "section": sections}) \
            .groupby("source"):
        per_source[src] = dict(sorted(set(zip(grp["section"],
                                              grp["section"].map(SECTION_TO_LABEL)))))
    return per_source


def add_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with a derived `category` column (hard 100% coverage)."""
    sections = [extract_section(u, s) for u, s in zip(df["Link"], df["source"])]
    unknown = sorted(set(sections) - set(SECTION_TO_LABEL))
    if unknown:
        raise ValueError(
            f"unknown URL sections ({len(unknown)}): {unknown[:20]}"
        )
    out = df.copy()
    out["category"] = [SECTION_TO_LABEL[s] for s in sections]
    return out


# ---------------------------------------------------------------------------
# Task 5: per-source boilerplate stripping
# ---------------------------------------------------------------------------

import re as _re

# Normalized single-space running text; nbsp collapsed for phrase matching.
_NSP = _re.compile(r"\s+")
_KOMPAS_DATELINE = _re.compile(
    r"^\s*(?:[A-Z][A-Za-z .,]*,\s*)?KOMPAS\.com\s*[–—-]+[\s\xa0]*")
_KOMPAS_BYLINE = _re.compile(r"\s*\(Reporter: [^)]*\)")
_GAMBAS = _re.compile(r"\s*\[Gambas:[^\]]*\]\s*")
_JUGA_PHRASE = _re.compile(r"(Simak juga|Lihat juga|Tonton juga)")


def _cut_detik_linkblog(t: str) -> str:
    """Cut detik link-blog fragments ("Simak/Lihat/Tonton juga ...").

    Measured behavior: a fragment introduces a related-video link — either a
    "[Gambas:...]" placeholder follows within ~300 chars (5,353 occurrences;
    cut from phrase through the placeholder) or the fragment dangles at the
    tail (39 occurrences; cut to end). Mid-body fragments with no placeholder
    (one measured article, 3 duplicate rows) are left in place: cutting their
    span to the end would eat real body text.
    """
    cuts: list[tuple[int, int]] = []
    for m in _JUGA_PHRASE.finditer(t):
        gambas = _GAMBAS.search(t, m.end(), m.end() + 300)
        if gambas:
            cuts.append((m.start(), gambas.end()))
        elif m.start() >= 0.85 * len(t):
            cuts.append((m.start(), len(t)))
    for a, b in reversed(cuts):
        t = t[:a] + " " + t[b:]
    return t

# Measured on the full CSV (query 2026-10-27):
#   tempo : "Baca berita dengan sedikit iklan"+"klik di sini" banners 94.1%
#           (start AND repeated mid/end), "Scroll ke bawah untuk melanjutkan
#           membaca" 89.1% (start and mid).
#   detik : "[Gambas:Video 20detik]" video placeholders 34.7%; link-blog
#           fragments ("Simak juga", "Lihat juga", "Tonton juga") 11.0%/9.9%
#           /6.4% of rows — fragment→[Gambas] pairs cut as one span, tail
#           danglers cut to end (39 occ.), mid-body without placeholder kept
#           (measured 1 article = 3 dup rows).
#   kompas: leading "JAKARTA, KOMPAS.com -" dateline 93.4% of rows
#           (replaceable prefix, no proxy ties), bylines 0.6% — both cut.
def strip_boilerplate(text: str, source: str) -> str:
    """Strip measured per-source boilerplate from one article body."""
    if not isinstance(text, str):
        return ""
    t = text.replace("\xa0", " ")
    if source == "tempo":
        t = t.replace("Scroll ke bawah untuk melanjutkan membaca", " ")
        t = t.replace("Baca berita dengan sedikit iklan", " ")
        t = t.replace("klik di sini", " ")
    elif source == "detik":
        t = _cut_detik_linkblog(t)
        t = _GAMBAS.sub(" ", t)
    elif source == "kompas":
        t = _KOMPAS_DATELINE.sub("", t)
        t = _KOMPAS_BYLINE.sub("", t)
    else:
        raise ValueError(f"unknown source: {source!r}")
    return _NSP.sub(" ", t).strip()


def strip_corpus(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with `Content` boilerplate-stripped per source.

    Rows are never dropped: short contents (<200 chars, 0.027% measured)
    are kept as-is (rendered meta-only downstream, PRD v1.1).
    """
    out = df.copy()
    out["Content"] = [
        strip_boilerplate(c, s)
        for c, s in zip(out["Content"], out["source"])
    ]
    lens = out["Content"].str.len()
    median = float(lens.median())
    if not median > 1_000:
        raise ValueError(
            f"post-strip median content length {median:.0f} <= 1000")
    return out
