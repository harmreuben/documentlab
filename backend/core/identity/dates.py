"""Date helpers shared by the MRZ, licence and comparison code."""
from __future__ import annotations

import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def yymmdd(value: str, kind: str, today: date) -> date | None:
    """Decode an MRZ YYMMDD date. Birth dates take the latest century not in the future;
    expiry dates are assumed to be this century."""
    if not re.fullmatch(r"\d{6}", value):
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:])
    if kind == "birth":
        year = 2000 + yy if 2000 + yy <= today.year else 1900 + yy
    else:
        year = 2000 + yy if 2000 + yy <= today.year + 50 else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def eight_digits(value: str) -> date | None:
    """Licence dates: MMDDCCYY (US) or CCYYMMDD (Canada). Whichever is a real date is used."""
    if not re.fullmatch(r"\d{8}", value):
        return None
    for build in (lambda v: date(int(v[4:]), int(v[:2]), int(v[2:4])),
                  lambda v: date(int(v[:4]), int(v[4:6]), int(v[6:]))):
        try:
            return build(value)
        except ValueError:
            continue
    return None


_PATTERNS = [
    (re.compile(r"\b(\d{1,2})\s*([A-Z]{3})[A-Z]*\s*/?\s*[A-Z]*\s+(\d{4})\b"), "dmy_text"),   # 12 AUG 1974, 12 AUG/AOUT 1974
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b"), "dmy"),                          # 12.08.1974, 12/08/1974
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),                                       # 1974-08-12
]


def dates_in_text(text: str) -> set[date]:
    """Every date that can be read from free text (as printed on documents)."""
    found = set()
    upper = text.upper()
    for pattern, kind in _PATTERNS:
        for m in pattern.finditer(upper):
            try:
                if kind == "dmy_text":
                    month = MONTHS.get(m.group(2)[:3])
                    if month:
                        found.add(date(int(m.group(3)), month, int(m.group(1))))
                elif kind == "dmy":
                    found.add(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
                else:
                    found.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except ValueError:
                continue
    return found


def nice(d: date | None) -> str:
    """12 August 1974 (no leading zero, works on every operating system)."""
    return f"{d.day} {d.strftime('%B %Y')}" if d else ""
