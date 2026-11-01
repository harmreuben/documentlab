"""Reads the common data elements from a driving-licence barcode, for comparison only.

Only the handful of fields needed to compare a licence with other documents are read
(name, dates, document number, sex). DocumentLab does not check the barcode's layout or
any jurisdiction's format rules: those checks belong to an authorised verification
provider, and are reported as unavailable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .checks import FAIL, PASS, UNAVAILABLE, Check, worst
from .dates import eight_digits, nice

# An element starts a line, follows a record separator, or directly follows the "DL"/"ID" section marker.
_ELEMENT = re.compile(r"(?:^|[\n\r\x1e]|(?<=DL)|(?<=ID))(D[A-Z]{2})([^\n\r\x1e]*)")
_NONE_VALUES = {"", "NONE", "UNAVL", "UNAVAILABLE"}
_FIELDS = {
    "DAQ": ("document_number", "Document number"),
    "DCS": ("surname", "Surname"),
    "DAC": ("first_name", "First name"),
    "DCT": ("first_name", "First name"),
    "DAD": ("middle_names", "Middle names"),
    "DBB": ("birth_date", "Date of birth"),
    "DBA": ("expiry_date", "Date of expiry"),
    "DBD": ("issue_date", "Date of issue"),
    "DBC": ("sex", "Sex"),
}
_SEX = {"1": ("M", "Male"), "2": ("F", "Female"), "9": ("X", "Unspecified")}


@dataclass
class LicenceResult:
    fields: dict = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(c.status for c in self.checks if c.category != "external")

    def as_dict(self) -> dict:
        return {"fields": self.fields, "checks": [c.as_dict() for c in self.checks], "status": self.status}


def read(payload: str, today: date | None = None) -> LicenceResult:
    today = today or date.today()
    found: dict[str, str] = {}
    for code, value in _ELEMENT.findall(payload):
        if code in _FIELDS and _FIELDS[code][0] not in found:
            found[_FIELDS[code][0]] = value.strip()

    result = LicenceResult()
    f, c = result.fields, result.checks
    for key in ("surname", "first_name", "middle_names", "document_number"):
        if found.get(key, "").upper() not in _NONE_VALUES:
            f[key] = {"label": dict(_FIELDS.values())[key], "value": found[key], "display": found[key]}
    given = " ".join(v for v in (found.get("first_name"), found.get("middle_names")) if v and v.upper() not in _NONE_VALUES)
    if given:
        f["given_names"] = {"label": "Given names", "value": given, "display": given}
    if found.get("sex"):
        code, label = _SEX.get(found["sex"], (found["sex"], found["sex"]))
        f["sex"] = {"label": "Sex", "value": code, "display": label}

    dates: dict[str, date | None] = {}
    for key in ("birth_date", "expiry_date", "issue_date"):
        raw = found.get(key)
        if raw is None:
            continue
        d = eight_digits(raw)
        dates[key] = d
        label = dict(_FIELDS.values())[key]
        f[key] = {"label": label, "value": d.isoformat() if d else raw, "display": nice(d) if d else raw}
        c.append(Check("dates", f"licence.{key}.valid", f"{label} is a real date", PASS if d else FAIL,
                       nice(d) if d else f"'{raw}' is not a real date."))

    c.append(Check("parsing", "licence.fields", "Fields needed for comparison",
                   PASS if {"surname", "birth_date"} <= f.keys() else FAIL,
                   f"Read {len(f)} field(s)." if {"surname", "birth_date"} <= f.keys() else
                   "The surname and date of birth weren't both found, so the licence can't be compared."))
    born, expires = dates.get("birth_date"), dates.get("expiry_date")
    if born and born > today:
        c.append(Check("dates", "licence.birth_in_past", "Date of birth is in the past", FAIL, "The date of birth is in the future."))
    if expires:
        c.append(Check("dates", "licence.not_expired", "Document has not expired", PASS if expires >= today else FAIL,
                       f"Valid until {nice(expires)}." if expires >= today else f"Expired on {nice(expires)}."))
    c.append(Check("external", "licence.jurisdiction_rules", "Issuer's format rules", UNAVAILABLE,
                   "Jurisdiction-specific rules are not checked by DocumentLab. Use an authorised verification provider."))
    return result
