"""US Social Security Number FORMAT checks.

This only says whether a number is shaped like an SSN that could have been issued. It
cannot say the number was issued, or to whom: that needs an authorised verification
service, which is reported as unavailable.

Rules (Social Security Administration):
  - 9 digits, written as AAA-GG-SSSS (hyphens or spaces optional)
  - area (AAA) is never 000 or 666, and never 900-999 (that range is used for ITINs)
  - group (GG) is never 00; serial (SSSS) is never 0000
  - some numbers were published in advertising and are invalid

The full number exists only inside `check()`. Results carry a masked form (last four digits).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .checks import FAIL, PASS, REVIEW, UNAVAILABLE, Check, worst

_SHAPE = re.compile(r"^(\d{3})([- ]?)(\d{2})\2(\d{4})$")
# Publicly circulated numbers that the SSA has declared invalid.
_PUBLISHED_INVALID = {"078051120", "219099999", "457555462"}
_EXAMPLE_NUMBERS = {"123456789"}

STATEMENT = ("A valid format does not show that this number was issued, or that it belongs to the person "
             "presenting it. Only an authorised verification service can confirm that.")


@dataclass
class SsnResult:
    format_valid: bool
    masked: str
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(c.status for c in self.checks if c.category != "external")

    def as_dict(self) -> dict:
        return {"format_valid": self.format_valid, "masked": self.masked, "status": self.status,
                "checks": [c.as_dict() for c in self.checks], "statement": STATEMENT}


def mask(digits: str) -> str:
    return f"***-**-{digits[-4:]}" if len(digits) >= 4 else "***-**-****"


def check(raw: str) -> SsnResult:
    text = (raw or "").strip()
    m = _SHAPE.match(text)
    digits = re.sub(r"\D", "", text)
    result = SsnResult(False, mask(digits) if len(digits) == 9 else "***-**-****")
    c = result.checks

    if not m:
        c.append(Check("data_format", "ssn.shape", "Nine digits as AAA-GG-SSSS", FAIL,
                       "Enter exactly 9 digits, optionally as AAA-GG-SSSS." if not digits.isdigit() or len(digits) != 9
                       else "Use hyphens or spaces consistently, or none at all."))
    else:
        area, group, serial = m.group(1), m.group(3), m.group(4)
        c.append(Check("data_format", "ssn.shape", "Nine digits as AAA-GG-SSSS", PASS, "Correct shape."))
        if area == "000" or area == "666":
            c.append(Check("data_format", "ssn.area", "Area number", FAIL, f"The area number is never {area}."))
        elif area >= "900":
            c.append(Check("data_format", "ssn.area", "Area number", FAIL,
                           "Area numbers 900-999 are not used for SSNs (that range is used for ITINs)."))
        else:
            c.append(Check("data_format", "ssn.area", "Area number", PASS, "Allowed."))
        c.append(Check("data_format", "ssn.group", "Group number", FAIL if group == "00" else PASS,
                       "The group number is never 00." if group == "00" else "Allowed."))
        c.append(Check("data_format", "ssn.serial", "Serial number", FAIL if serial == "0000" else PASS,
                       "The serial number is never 0000." if serial == "0000" else "Allowed."))
        if digits in _PUBLISHED_INVALID:
            c.append(Check("data_format", "ssn.published", "Not a published example", FAIL,
                           "This number was printed in advertising and has been declared invalid."))
        elif digits in _EXAMPLE_NUMBERS:
            c.append(Check("data_format", "ssn.published", "Not a published example", REVIEW,
                           "This is a widely used example number. Treat it as test data."))
    result.format_valid = all(x.status != FAIL for x in c)
    c.append(Check("external", "ssn.external", "Issued to this person", UNAVAILABLE,
                   "No authorised verification service is connected, so ownership isn't checked."))
    return result
