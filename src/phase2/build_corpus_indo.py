"""Build the phase-2 Indo catalog: CSV -> dedupe/categories/strip -> tokens.

CLI:
  python -m src.phase2.build_corpus_indo [--slice N] [--workers W] [--out PATH]

Writes `data/processed/indo/catalog.parquet` (nid, title, content,
processed_text, category, source, published_at, split="unsplit") and
`docs/evidence/phase2/build_summary.json`. The nid scheme and hard asserts
follow `data/DATASET_LOCK_INDO.md`; a collision is a build failure.

Stemming runs in parallel over the unique pure-alpha vocabulary only (each
word once, 0.3 s alarm per word); per-document stopword masking runs in
parallel afterward against the injected stem cache, mirroring v1's two-phase
portable build without importing the frozen `src/preprocessing` package.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from multiprocessing import Pool

import pandas as pd

from src.phase2 import config
from src.phase2.corpus import add_categories, dedupe, strip_corpus
from src.phase2.textproc import IndoPreprocessor, clean_text, is_stemmable
from src.phase2.timeparse import parse_waktu

REPO = Path(__file__).resolve().parents[2]
SUMMARY_OUT = REPO / "docs/evidence/phase2/build_summary.json"
EXPECTED_UNIQUE = 67_381  # measured in the lock; any drift = hard failure

_PREP = None
_CACHE: dict[str, str] = {}


def _init_stem_worker():
    global _PREP
    _PREP = IndoPreprocessor()


def _stem_one(word: str) -> str:
    return _PREP._stem_word(word)


def _init_mask_worker(stem_map: dict[str, str]):
    global _PREP
    _PREP = IndoPreprocessor()
    _PREP.use_cache(stem_map)


def _mask_one(cleaned: str) -> str:
    return _PREP.mask_stemmed(_PREP.assemble(cleaned))


def make_nid(url: str) -> str:
    return "I" + hashlib.sha1(url.encode()).hexdigest()[:10]


def load_raw(slice_n: int | None = None) -> pd.DataFrame:
    cols = ["Judul", "Waktu", "Link", "Content", "source"]
    df = pd.read_csv(REPO / config.RAW_CSV, usecols=cols)
    if slice_n is None:
        return df
    # deterministic slice: first N rows by sorted URL (stable, no RNG)
    return df.sort_values("Link", kind="mergesort").head(slice_n).reset_index(drop=True)


def build(slice_n: int | None = None, workers: int = 8) -> tuple[pd.DataFrame, dict]:
    t0 = time.time()
    raw = load_raw(slice_n)
    n_raw = len(raw)
    work = strip_corpus(add_categories(dedupe(raw)))
    work["nid"] = work["Link"].map(make_nid)
    work["title"] = work["Judul"].fillna("")
    work["content"] = work["Content"].fillna("")
    work["published_at"] = pd.to_datetime(
        [parse_waktu(w) for w in work["Waktu"]], utc=True)
    work["split"] = "unsplit"

    # Phase A: clean text (regex only) in parallel over documents.
    t_clean = time.time()
    if workers <= 1 or len(work) < 1_000:
        cleaned = [clean_text(t) for t in work["content"].tolist()]
    else:
        with Pool(workers) as pool:
            cleaned = pool.map(clean_text, work["content"].tolist(), chunksize=500)
    t_clean = time.time() - t_clean

    # Phase B: stem each unique pure-alpha token once (parallel, cache per worker).
    t_stem = time.time()
    vocab = sorted({w for doc in cleaned for w in doc.split()})
    stemmable = [w for w in vocab if is_stemmable(w)]
    if workers <= 1 or len(work) < 1_000:
        prep = IndoPreprocessor()
        stem_map = {w: prep._stem_word(w) for w in stemmable}
    else:
        with Pool(workers, initializer=_init_stem_worker) as pool:
            stemmed = (pool.map(_stem_one, stemmable, chunksize=200)
                       if stemmable else [])
        stem_map = dict(zip(stemmable, stemmed))
    t_stem = time.time() - t_stem

    # Phase C: assemble -> stopword mask -> filter, parallel with warm cache.
    t_mask = time.time()
    if workers <= 1 or len(work) < 1_000:
        prep = IndoPreprocessor()
        prep.use_cache(stem_map)
        processed = [prep.mask_stemmed(prep.assemble(doc)) for doc in cleaned]
    else:
        with Pool(workers, initializer=_init_mask_worker,
                  initargs=(stem_map,)) as pool:
            processed = pool.map(_mask_one, cleaned, chunksize=500)
    t_mask = time.time() - t_mask

    work["processed_text"] = processed
    catalog = work[["nid", "title", "content", "processed_text",
                    "category", "source", "published_at", "split"]].copy()

    if catalog["nid"].duplicated().any():
        dupes = catalog.loc[catalog["nid"].duplicated(), "nid"].tolist()
        raise ValueError(f"nid collision (build failed): {dupes[:5]}")
    if slice_n is None and len(catalog) != EXPECTED_UNIQUE:
        raise ValueError(
            f"unique catalog count {len(catalog)} != lock {EXPECTED_UNIQUE}")

    summary = {
        "raw_rows": int(n_raw),
        "unique_rows": int(len(catalog)),
        "unique_nids": int(catalog["nid"].nunique()),
        "per_source": catalog["source"].value_counts().to_dict(),
        "category_counts": catalog["category"].value_counts().to_dict(),
        "median_content_chars": float(catalog["content"].str.len().median()),
        "median_processed_tokens": float(
            catalog["processed_text"].str.split().str.len().median()),
        "vocab_unique": len(vocab),
        "vocab_stemmed": len(stemmable),
        "slice_n": slice_n,
        "workers": workers,
        "seconds": {"clean": round(t_clean, 1), "stem": round(t_stem, 1),
                    "mask": round(t_mask, 1), "total": round(time.time() - t0, 1)},
    }
    return catalog, summary


def write_outputs(catalog: pd.DataFrame, summary: dict,
                  out_path: Path | None = None,
                  summary_path: Path | None = None) -> Path:
    out = Path(out_path) if out_path else REPO / config.CATALOG_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_parquet(out, index=False)
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    summary["catalog_path"] = str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out)
    summary["catalog_sha256"] = sha
    smry = Path(summary_path) if summary_path else SUMMARY_OUT
    smry.parent.mkdir(parents=True, exist_ok=True)
    smry.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m src.phase2.build_corpus_indo",
        description="Build the phase-2 Indo catalog parquet.")
    ap.add_argument("--slice", type=int, default=None,
                    help="validate on the first N URLs only (no lock assert)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=str, default=None,
                    help="override output parquet path")
    ap.add_argument("--summary-out", type=str, default=None,
                    help="override build summary JSON path (tests/dev)")
    args = ap.parse_args(argv)

    catalog, summary = build(slice_n=args.slice, workers=args.workers)
    out = write_outputs(catalog, summary,
                        Path(args.out) if args.out else None,
                        Path(args.summary_out) if args.summary_out else None)
    print(f"catalog: {len(catalog)} rows -> {out}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
