"""Build the small nid -> portal-link table used by the article detail page.

  python -m src.phase2.build_links

The catalogue cannot carry a `url` column without changing its recorded
sha256, so the link is reconstructed from the raw CSV at runtime
(`nid = "I" + sha1(link)[:10]`). That CSV is 207 MB; the deployment image
should not carry it just to render one attribution line. This command writes
the same mapping as a 3.2 MB parquet (nid, url) that `build_source_urls`
prefers when present.

Derived, not locked: deleting the file only removes the source links (the
detail page then shows the portal name without a hyperlink). The raw CSV
remains the source of truth.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from src.phase2 import config

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data/processed/indo/source_links.parquet"


def make_nid(link: str) -> str:
    return "I" + hashlib.sha1(link.encode()).hexdigest()[:10]


def build_links(raw_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(raw_csv, usecols=["Link"])
    urls = df["Link"].dropna().astype(str).str.strip()
    urls = urls[urls != ""].drop_duplicates()
    out = pd.DataFrame({"url": urls})
    out["nid"] = out["url"].map(make_nid)
    # A nid collision would silently point one article at another portal page.
    assert out["nid"].is_unique, "nid collision in link map"
    return out[["nid", "url"]].sort_values("nid").reset_index(drop=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m src.phase2.build_links",
        description="Write data/processed/indo/source_links.parquet "
                    "(nid -> original portal URL).")
    ap.add_argument("--raw", default=config.RAW_CSV)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    raw = Path(args.raw) if Path(args.raw).is_absolute() else REPO / args.raw
    if not raw.exists():
        raise SystemExit(f"raw CSV missing: {raw}")
    links = build_links(raw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    links.to_parquet(out, index=False, compression="zstd")
    print(f"{len(links)} links -> {out} ({out.stat().st_size / 1048576:.1f} MB)")


if __name__ == "__main__":
    main()
