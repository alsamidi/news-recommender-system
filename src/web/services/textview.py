"""Text presentation helpers for the web layer (no corpus changes).

Two display-only jobs live here, both applied at render time so the frozen
research artifacts keep their exact bytes:

1. `strip_leading_dateline` — 23,198 of 67,381 articles (34.4%, and 90.7% of
   the Tempo rows) begin with a comma left over from the removed dateline:
   `", TEMPO.CO, Jakarta - Dosen ..."`. The comma is residue of a preprocessing
   step, not part of the sentence. Fixing it in the corpus would change
   `catalog.parquet`, invalidate the sha256 in `DATASET_LOCK_INDO.md`, and force
   Gate A/B/C, the split, ALS and every evaluation number to be recomputed, so
   it is corrected here instead (measured: 0 such rows in detik/kompas).

2. `source_url` — the catalogue has no `url` column, but `nid` is defined as
   `"I" + sha1(Link)[:10]` in `src/phase2/build_corpus_indo.py`, so the original
   portal link is recoverable exactly. Verified: all 67,381 catalogue nids map
   back to a row of `data/raw/final_merge_dataset.csv` (100%), no empty links.
   The link is only rendered on the detail page, after the body, as plain
   attribution text (PRD §10.3 as amended in v1.3).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

RAW_CSV = "data/raw/final_merge_dataset.csv"

# Leading punctuation that belongs to a dateline, never to a sentence. Kept
# narrow on purpose: stripping arbitrary punctuation could eat a legitimate
# opening quote or bracket.
_LEADING_JUNK = (",", ";", ":")


def strip_leading_dateline(text: str | None) -> str | None:
    """Remove dateline residue from the start of an article body.

    Only leading commas/semicolons/colons (with the whitespace around them)
    are removed, repeatedly, so `", , TEMPO.CO, Jakarta - ..."` also cleans up.
    Text is otherwise untouched — no paragraph reflow, no truncation.
    """
    if not text:
        return text
    out = text.lstrip()
    # Strip junk repeatedly, re-trimming after each cut: `", , TEMPO.CO"` leaves
    # a leading space after the second comma, which would otherwise survive.
    while out and out[0] in _LEADING_JUNK:
        out = out[1:].lstrip()
    return out


def _nid_for(link: str) -> str:
    return "I" + hashlib.sha1(link.encode()).hexdigest()[:10]


def build_source_urls(catalog_nids: set[str],
                      raw_csv: str = RAW_CSV) -> dict[str, str]:
    """`nid -> original portal link`, for nids that are in the catalogue.

    The mapping is derived, not stored: `nid` is a sha1 of the link, so reading
    only the `Link` column of the raw CSV (1.2 s, 207 MB file) reconstructs it
    without touching any processed artifact. Missing CSV or a nid that does not
    map back simply yields no link — the detail page then shows the source name
    without a hyperlink rather than inventing a URL.
    """
    path = Path(raw_csv)
    if not path.exists():
        return {}

    df = pd.read_csv(path, usecols=["Link"])
    out: dict[str, str] = {}
    for link in df["Link"].dropna():
        link = str(link).strip()
        if not link:
            continue
        nid = _nid_for(link)
        if nid in catalog_nids:
            out[nid] = link
    return out
