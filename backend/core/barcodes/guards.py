"""Refuses payloads laid out like government identity documents.

DocumentLab generates generic barcodes and neutral test payloads only. It must not
produce driver's licence / ID-card barcode data (AAMVA-style layouts) or passport
machine-readable zones. This check runs on every payload, in every format, before
anything is rendered.

The patterns look for the structure of those layouts, not for single words, so
ordinary text that happens to contain "ANSI" or "DAQ" is not blocked.
"""
from __future__ import annotations

import re

IDENTITY_LAYOUT_MESSAGE = (
    "This data is laid out like a driver's licence, ID card or passport. DocumentLab only "
    "generates generic barcodes and neutral test data, so it won't encode it."
)

# AAMVA-style header: "ANSI " or "AAMVA" followed by a 6-digit issuer number.
_ISSUER_HEADER = re.compile(r"(ANSI|AAMVA)\s*\d{6}", re.IGNORECASE)
# Compliance indicator at the very start: "@" then line feed / record separator / carriage return.
_COMPLIANCE_START = re.compile(r"^\s*@[\n\x1e\r]")
# Subfile designator such as "DL00410278" or "ID00410278".
_SUBFILE = re.compile(r"\b(DL|ID)\d{8}")
# Data element identifiers (three capitals starting with D, then a value), e.g. "DAQ...", "DCS...".
_ELEMENT = re.compile(r"(?:^|[\n\r\x1e])D[A-D][A-Z][^\n\r\x1e]+")
# Machine-readable zone line: 30, 36 or 44 characters of A-Z 0-9 < containing a "<<" filler.
_MRZ_LINE = re.compile(r"^[A-Z0-9<]{30}$|^[A-Z0-9<]{36}$|^[A-Z0-9<]{44}$")
_MRZ_JOINED = re.compile(r"^[A-Z0-9<]{60,132}$")


def identity_layout_reason(payload: str) -> str | None:
    """Return a short internal reason if the payload looks like an identity-document layout."""
    if _ISSUER_HEADER.search(payload):
        return "issuer header"
    if _COMPLIANCE_START.search(payload):
        return "compliance indicator"
    if _SUBFILE.search(payload) and _ELEMENT.search(payload):
        return "subfile designator"
    if len(_ELEMENT.findall(payload)) >= 3:
        return "data element identifiers"

    lines = [line.strip() for line in payload.replace("\r", "\n").split("\n") if line.strip()]
    mrz_lines = [line for line in lines if _MRZ_LINE.match(line) and "<<" in line]
    if len(mrz_lines) >= 2:
        return "machine-readable zone"
    compact = "".join(payload.split())
    if _MRZ_JOINED.match(compact) and compact.count("<") >= 8 and len(compact) in (60, 72, 88, 90, 108, 132):
        return "machine-readable zone"
    return None
