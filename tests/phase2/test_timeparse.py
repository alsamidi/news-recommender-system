import pandas as pd
import pytest

from src.phase2.timeparse import parse_waktu

REAL_FORMATS = [
    # tempo (pipe separator, dot-time, and date-only variant)
    ("16 Juli 2025 | 10.17 WIB", (2025, 7, 16, 10, 17)),
    ("1 September 2025", (2025, 9, 1, 0, 0)),
    # detik (day-name prefix, abbrev months incl. both Agu/ags)
    ("Sabtu, 02 Agu 2025 21:23 WIB", (2025, 8, 2, 21, 23)),
    ("Senin, 12 Agu 2024 21:58 WIB", (2024, 8, 12, 21, 58)),
    ("Senin, 24 Mar 2025 22:41 WIB", (2025, 3, 24, 22, 41)),
    # kompas (date only, long months)
    ("6 September 2025", (2025, 9, 6, 0, 0)),
    ("29 November 2024", (2024, 11, 29, 0, 0)),
    # rare numeric kompas variant; dd/mm order proven vs URL date path
    ("12/02/2025", (2025, 2, 12, 0, 0)),
]


@pytest.mark.parametrize("raw,expect", REAL_FORMATS)
def test_real_portal_formats(raw, expect):
    dt = parse_waktu(raw)
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == expect
    assert dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0


def test_all_months_long_and_abbrev():
    assert parse_waktu("1 Januari 2025").month == 1
    assert parse_waktu("1 Februari 2025").month == 2
    assert parse_waktu("1 Desember 2025").month == 12
    assert parse_waktu("1 Agu 2025").month == 8
    assert parse_waktu("1 ags 2025").month == 8
    assert parse_waktu("1 Okt 2025").month == 10


@pytest.mark.parametrize("raw", ["", "   ", "garbage", "32 Agustus 2025", None])
def test_garbage_raises(raw):
    with pytest.raises(ValueError):
        parse_waktu(raw)


def test_integration_1000_real_rows():
    """100% parse on 1,000 random real CSV rows (seed=42)."""
    df = pd.read_csv("data/raw/final_merge_dataset.csv", usecols=["Waktu"])
    sample = df["Waktu"].astype(str).sample(n=1000, random_state=42)
    fails = []
    for raw in sample:
        try:
            parse_waktu(raw)
        except ValueError as e:
            fails.append((raw, str(e)))
    assert not fails, f"{len(fails)}/1000 failed: {fails[:3]}"
