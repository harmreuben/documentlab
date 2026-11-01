"""Compares the same fields across several documents. Source values are never changed.

Names are compared after removing accents, punctuation and case. A near match (for example a
truncated MRZ name or one misread letter) is REVIEW_REQUIRED, never PASS. Document numbers and
expiry dates are only compared between documents of the same type, because a passport and a
licence legitimately have different ones.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .checks import FAIL, NOT_CHECKED, PASS, REVIEW, worst

FIELDS = [
    ("surname", "Surname", "name", False),
    ("given_names", "Given names", "name", False),
    ("birth_date", "Date of birth", "exact", False),
    ("sex", "Sex", "exact", False),
    ("document_number", "Document number", "exact", True),   # True = same document type only
    ("expiry_date", "Date of expiry", "exact", True),
]
NEAR = 0.85


def normalise_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    return re.sub(r"[^A-Z]+", " ", text).strip()


def _compare_names(a: str, b: str) -> tuple[str, float, str]:
    na, nb = normalise_name(a), normalise_name(b)
    if na == nb:
        return PASS, 1.0, "Same name."
    if na and nb and (na.startswith(nb) or nb.startswith(na)):
        return REVIEW, 0.9, "One name is a shortened form of the other (MRZ names can be truncated)."
    ratio = SequenceMatcher(None, na, nb).ratio()
    if ratio >= NEAR:
        return REVIEW, ratio, "Nearly the same; a letter may have been misread or transliterated differently."
    return FAIL, ratio, "Different names."


ACTIONS = {
    PASS: "None.",
    REVIEW: "Look at both documents and confirm whether this is the same value.",
    FAIL: "Check both documents. The values differ; this may be a different person or a data-entry error.",
    NOT_CHECKED: "None.",
}


def compare(documents: list[dict]) -> dict:
    """documents: [{"reference", "document_type", "fields": {name: {"value", ...}}}, ...] (2 or more)."""
    first = documents[0]
    rows = []
    for key, label, mode, same_type_only in FIELDS:
        values = [{"reference": d["reference"], "document_type": d["document_type"],
                   "value": (d["fields"].get(key) or {}).get("value", "")} for d in documents]
        present = [v for v in values if v["value"]]
        row = {"field": key, "label": label, "values": values, "status": NOT_CHECKED, "confidence": None,
               "reason": "", "action": ACTIONS[NOT_CHECKED]}
        if len(present) < 2:
            row["reason"] = "Not available on at least two documents."
        elif same_type_only and len({v["document_type"] for v in present}) > 1:
            row["reason"] = "Only compared between documents of the same type."
        else:
            results = []
            base = present[0]["value"]
            for other in present[1:]:
                if mode == "name":
                    results.append(_compare_names(base, other["value"]))
                else:
                    same = str(base).upper() == str(other["value"]).upper()
                    results.append((PASS if same else FAIL, 1.0 if same else 0.0, "Same value." if same else "Different values."))
            status = worst(r[0] for r in results)
            pick = next(r for r in results if r[0] == status)
            row.update(status=status, confidence=round(min(r[1] for r in results), 2), reason=pick[2], action=ACTIONS[status])
        rows.append(row)

    checked = [r["status"] for r in rows if r["status"] != NOT_CHECKED]
    overall = worst(checked) if checked else NOT_CHECKED
    counts = {s: sum(r["status"] == s for r in rows) for s in (PASS, REVIEW, FAIL)}
    summary = (f"{counts[PASS]} field(s) match, {counts[REVIEW]} need review and {counts[FAIL]} differ "
               f"across {len(documents)} documents.")
    return {"status": overall, "summary": summary, "rows": rows, "reference_document": first["reference"]}
