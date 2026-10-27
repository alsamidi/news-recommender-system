"""Popularity ranking for the no-history feed.

Approved decision (2026-10-20):
- computed ONCE at application startup, then cached in memory
- rank by descending summed `weight`, tie-break `nid` ascending
- keep only nids present in the catalog
- never at module-import time
- no popular.json artifact
- fail loudly if the training interactions cannot be loaded
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

TRAIN_INTERACTIONS = Path("data/processed/interactions_train.parquet")


class PopularityUnavailable(RuntimeError):
    """Raised when the popularity source cannot be built at startup."""


def _era_source() -> tuple[Path, str]:
    """(parquet path, weight column) for the serving era.

    SERVING_ERA=mind keeps the frozen MIND train parquet (`weight` =
    summed click weights); default = indo corpus, where every view is one
    event, so the weight column is derived as 1 per row — identical to the
    evaluated popularity baseline (train view counts desc, nid asc).
    """
    if os.environ.get("SERVING_ERA", "").lower() == "mind":
        return Path("data/processed/interactions_train.parquet"), "weight"
    return Path("data/processed/indo/interactions_train.parquet"), None


class Popularity:
    """Immutable ranking of catalog nids by train click weight."""

    def __init__(self, ranked_nids: list[str]):
        self._ranked = tuple(ranked_nids)

    def __len__(self) -> int:
        return len(self._ranked)

    @property
    def ranked(self) -> tuple[str, ...]:
        return self._ranked

    @classmethod
    def build(cls, interactions_path: Path | str | None = None,
              catalog_nids: set[str] | None = None) -> "Popularity":
        if interactions_path is None:
            path, weight_col = _era_source()
        else:
            path, weight_col = Path(interactions_path), "weight"
        if not path.exists():
            raise PopularityUnavailable(
                f"popularity source missing: {path}. "
                "Generate the train interactions parquet first."
            )
        try:
            if weight_col:
                df = pd.read_parquet(path, columns=["nid", weight_col]) \
                       .rename(columns={weight_col: "weight"})
            else:
                df = pd.read_parquet(path, columns=["nid"])
                df["weight"] = 1  # indo: one view = one event
        except Exception as exc:  # corrupt/partial file
            raise PopularityUnavailable(
                f"cannot read popularity source {path}: {exc}"
            ) from exc
        return cls.from_frame(df, catalog_nids)

    @classmethod
    def from_frame(cls, df: "pd.DataFrame",
                   catalog_nids: set[str] | None = None) -> "Popularity":
        """Build from an already-loaded frame (used by tests)."""
        df = df[["nid", "weight"]].copy()
        if df.empty:
            raise PopularityUnavailable("popularity source is empty")

        if catalog_nids is not None:
            df = df[df["nid"].isin(catalog_nids)]
            if df.empty:
                raise PopularityUnavailable(
                    "no interaction nids intersect the catalog; "
                    "catalog and dataset are out of sync"
                )

        sums = df.groupby("nid", as_index=True)["weight"].sum()
        # Single sort: weight desc, nid asc for determinism.
        ranked = sorted(sums.index, key=lambda n: (-sums[n], n))
        return cls(ranked)

    def top(self, limit: int) -> list[str]:
        return list(self._ranked[:limit])

    def filter_out(self, exclude: set[str]) -> "Popularity":
        return Popularity([n for n in self._ranked if n not in exclude])
