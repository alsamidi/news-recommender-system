"""Corpus assembly: strict URL dedupe with content-identity assert."""
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
