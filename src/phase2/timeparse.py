"""Indonesian datetime parser for portal "Waktu" strings.

Handles the three measured portal formats:
  tempo : "16 September 2025 | 10.17 WIB"   (also without time)
  detik : "Sabtu, 02 Agu 2025 21:23 WIB"    (day-name prefix, abbrev months)
  kompas: "6 September 2025"                (date only, long months)

Returns a tz-aware UTC datetime. Measured-uncertainty decision (stated, not
hidden): the source strings carry "WIB" with no numeric offset, and Kompas
carries no time at all. The parser keeps the wall clock as printed and labels
it UTC — i.e. every timestamp may be systematically off by -7h from true UTC
(WIB = UTC+7). Relative ordering within a source is unaffected by this
constant shift; the Kompas missing-time case (midnight default) is the larger
quantization (up to ~24h within-day). This is accepted for MVP ranking.
"""
import re
from datetime import datetime, timezone

MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12,
    # measured abbreviations ("Agu" and "ags" both occur on detik)
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "agu": 8, "ags": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

_YEAR = re.compile(r"(20\d{2})")
_MONTH = re.compile(r"([A-Za-z]{3,9})")
_DAY = re.compile(r"\b(\d{1,2})\b")
_TIME = re.compile(r"(\d{1,2})[.:](\d{2})")
_NUMERIC = re.compile(r"^(\d{1,2})/(\d{1,2})/(20\d{2})$")


def parse_waktu(s: str) -> datetime:
    """Parse one Waktu string into a tz-aware UTC datetime.

    Raises ValueError on empty or garbage input rather than guessing.
    """
    if not isinstance(s, str) or not s.strip():
        raise ValueError("unparseable Waktu: empty/None")
    # Rare numeric variant (15 measured kompas rows, "12/02/2025"): dd/mm/yyyy,
    # order proven against the URL date path (2025/02/12) on real rows.
    num = _NUMERIC.match(s.strip())
    if num:
        return datetime(int(num.group(3)), int(num.group(2)),
                        int(num.group(1)), tzinfo=timezone.utc)
    y = _YEAR.search(s)
    # Day-name prefixes ("Sabtu,") must not shadow the real month token:
    # accept the first alpha token that is a known Indonesian month word.
    m = next((mo for mo in _MONTH.finditer(s) if mo.group(1).lower() in MONTHS), None)
    if not (y and m):
        raise ValueError(f"unparseable Waktu (year/month): {s!r}")

    # Day: the 1-2 digit number adjacent to the month token on either side,
    # skipping the year itself. "6 September 2025" -> 6; "02 Agu 2025" -> 2.
    month_span = m.span()
    day = None
    for mo in _DAY.finditer(s):
        if month_span[0] <= mo.start() < month_span[1]:
            continue
        if mo.start() < month_span[0]:
            day = int(mo.group(1))
            break
    if day is None:  # date-then-time layouts: take first day after month
        for mo in _DAY.finditer(s):
            if month_span[0] <= mo.start() < month_span[1]:
                continue
            day = int(mo.group(1))
            break
    if day is None:
        raise ValueError(f"unparseable Waktu (day): {s!r}")

    t = _TIME.search(s)
    hh, mm = (int(t.group(1)), int(t.group(2))) if t else (0, 0)
    try:
        dt = datetime(int(y.group(1)), MONTHS[m.group(1).lower()], day,
                      hh, mm, tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(f"unparseable Waktu (invalid date): {s!r}") from e
    return dt
