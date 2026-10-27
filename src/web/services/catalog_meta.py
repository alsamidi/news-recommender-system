"""Display metadata for articles: `source` and publication date.

Why this module exists (PRD v1.1 §10.2, approved 2026-10-27)
-----------------------------------------------------------
The active corpus carries `source` (kompas/tempo/detik) and a real
publication date. Both are *display* fields: they are shown as plain text
and never used for scoring. The frozen API contract v1.0.0 has no field for
them (`ArticleDetailResponse` is title/abstract/category/subcategory), and
extending it would need a version bump. The web layer therefore reads the
active catalog directly, exactly as `popular.py` and `stats.py` already read
their parquet sources at startup.

What is never done here (PRD §10.3):
- no author, no portal URL, no thumbnail — the corpus has none, and inventing
  one is forbidden;
- no derived counts: article counts come from `data/DATASET_LOCK_INDO.md`,
  never from a constant in code.
"""
from __future__ import annotations

import os
from pathlib import Path

MONTHS_ID = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
             "Jul", "Agu", "Sep", "Okt", "Nov", "Des")

CATALOG_PATH = "data/processed/indo/catalog.parquet"


def _serving_era() -> str:
    """Mirror of `api.main._serving_era`; MIND is opt-in only."""
    return "mind" if os.environ.get("SERVING_ERA", "").lower() == "mind" \
        else "indo"


def format_published_at(value) -> str | None:
    """Render a catalog publication timestamp as `19 Okt 2025`.

    Catalogue dates are day-resolution (parsed from a date column), so the
    time of day is deliberately dropped: printing 00:00 would imply a
    precision the source does not have.
    """
    if value is None:
        return None
    try:
        dt = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    except (ValueError, TypeError):
        return None
    try:
        return f"{dt.day} {MONTHS_ID[dt.month - 1]} {dt.year}"
    except (AttributeError, IndexError, TypeError):
        return None


def build_article_meta() -> dict[str, dict]:
    """`nid -> {"source", "source_label", "published_at", "published_text"}`.

    Built once at startup (67k rows, ~0.3 s) and read-only afterwards. The
    MIND era has neither field, so it returns an empty map and every card
    keeps its old shape — the seam stays era-aware rather than branching in
    templates.

    `source_label` is title-cased for display ("Sumber: Kompas"): the corpus
    stores lowercase portal slugs, and lowercasing a proper noun on screen
    reads as a typo, not as data.
    """
    if _serving_era() == "mind":
        return {}

    import pandas as pd

    path = Path(CATALOG_PATH)
    if not path.exists():
        raise RuntimeError(
            f"catalog missing: {path}. Build the indo corpus first "
            "(python -m src.phase2.build_corpus_indo)."
        )
    df = pd.read_parquet(path, columns=["nid", "source", "published_at"])
    out: dict[str, dict] = {}
    for nid, source, published in zip(df["nid"], df["source"],
                                      df["published_at"]):
        text = format_published_at(published)
        out[str(nid)] = {
            "source": str(source) if source is not None else None,
            "source_label": str(source).capitalize() if source else None,
            "published_at": published,
            "published_text": text,
        }
    return out


def attach_article_meta(meta: dict[str, dict], rows: list[dict],
                        cards: bool) -> list[dict]:
    """Merge display metadata into rows, in place, and return them.

    `cards=True` is a card context: PRD §10.2 restricts a card to
    title + meta (category/source/date), so the excerpt is dropped. The
    detail page calls with `cards=False` and keeps the full text.
    """
    for row in rows:
        extra = meta.get(row.get("nid") or "", {})
        # Deliberately no `row["source"] = ...`: history rows already carry
        # the *interaction* source (feed/similar/history/direct) under that
        # key, and the catalogue source is displayed from `source_label`.
        row["source_label"] = extra.get("source_label")
        row["published_at"] = extra.get("published_at")
        row["published_text"] = extra.get("published_text")
        if cards and extra:
            # Indo cards carry no excerpt by decision (§10.2); MIND cards have
            # no metadata entry at all, so their abstract survives untouched.
            row.pop("abstract", None)
    return rows
