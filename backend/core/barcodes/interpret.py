"""Explains what a decoded payload contains and checks its data format.

Recognised content:
  identity_document  laid out like a licence, ID card or passport: not displayed or stored here
  documentlab_schema JSON in one of DocumentLab's neutral schemas: fields validated
  gs1_retail         EAN-13 / EAN-8 / UPC-A number: check digit recomputed
  url                a web address (never opened)
  text               printable text
  binary             non-printable bytes
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .guards import identity_layout_reason
from .issues import Issues
from .schemas import get_schema, build_payload
from .symbologies import gs1_check_digit

PASS, FAIL, REVIEW, NOT_CHECKED = "PASS", "FAIL", "REVIEW_REQUIRED", "NOT_CHECKED"


@dataclass
class Interpretation:
    kind: str
    summary: str
    data_check: str = NOT_CHECKED   # PASS | FAIL | REVIEW_REQUIRED | NOT_CHECKED
    data_detail: str = ""
    fields: list[dict] = field(default_factory=list)  # [{"label", "value"}] for display
    notes: list[str] = field(default_factory=list)
    sensitive: bool = False

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def interpret(format_key: str | None, text: str, raw: bytes) -> Interpretation:
    if identity_layout_reason(text):
        return Interpretation(
            "identity_document", "Identity document data",
            REVIEW, "This barcode holds data laid out like a driver's licence, ID card or passport. "
                    "It is not displayed or stored by the Barcode Analyzer.",
            sensitive=True,
        )

    if format_key in ("ean13", "ean8", "upca"):
        return _gs1(format_key, text)

    stripped = text.strip()
    if stripped.startswith("{"):
        result = _documentlab_json(stripped)
        if result:
            return result

    if stripped.lower().startswith(("http://", "https://")):
        parts = urlsplit(stripped)
        notes = ["Links are shown, never opened."]
        if parts.scheme == "http":
            notes.append("This link is not encrypted (http, not https).")
        return Interpretation("url", "Web address", NOT_CHECKED, "",
                              [{"label": "Site", "value": parts.netloc}, {"label": "Path", "value": parts.path or "/"}],
                              notes)

    if text and all(c.isprintable() or c in "\r\n\t" for c in text):
        return Interpretation("text", "Plain text", NOT_CHECKED, "",
                              [{"label": "Characters", "value": str(len(text))}])

    return Interpretation("binary", "Binary data", NOT_CHECKED, "",
                          [{"label": "Bytes", "value": str(len(raw))},
                           {"label": "First bytes (hex)", "value": raw[:24].hex(" ")}],
                          ["The data contains non-printable characters, so it is shown as bytes."])


def _gs1(format_key: str, text: str) -> Interpretation:
    lengths = {"ean13": 13, "ean8": 8, "upca": 12}
    digits = text
    notes = []
    if format_key == "ean13" and len(text) == 13 and text.startswith("0"):
        notes.append(f"Starts with 0, so it is also a valid UPC-A number: {text[1:]}.")
    if not digits.isdigit() or len(digits) != lengths[format_key]:
        return Interpretation("gs1_retail", "Retail product number", FAIL,
                              f"Expected {lengths[format_key]} digits, found '{text}'.", notes=notes)
    expected = gs1_check_digit(digits[:-1])
    fields = [{"label": "Number", "value": digits[:-1]}, {"label": "Check digit", "value": digits[-1]}]
    if digits[0] == "2" or (format_key == "upca" and digits[0] == "4"):
        notes.append("This number is in a range reserved for internal use (in-store or restricted circulation).")
    if digits[-1] != expected:
        return Interpretation("gs1_retail", "Retail product number", FAIL,
                              f"The check digit is {digits[-1]} but should be {expected}.", fields, notes)
    return Interpretation("gs1_retail", "Retail product number", PASS, "The check digit is correct.", fields, notes)


def _documentlab_json(text: str) -> Interpretation | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("schema"), str):
        return None
    schema = get_schema(data["schema"])
    if schema is None or not schema.structured:
        return Interpretation("json", "JSON data", NOT_CHECKED, "",
                              [{"label": k, "value": str(v)} for k, v in list(data.items())[:20]],
                              [f"The schema '{data['schema']}' is not a DocumentLab schema, so its fields weren't checked."])

    values = {k: ("" if v is None else str(v)) for k, v in data.items() if k != "schema"}
    issues = Issues()
    canonical = build_payload(schema, values, issues)
    labels = {f.name: f.label for f in schema.fields}
    fields = [{"label": labels.get(k, k), "value": str(v)} for k, v in data.items() if k != "schema"]
    if not issues.ok:
        return Interpretation("documentlab_schema", schema.name, FAIL,
                              "; ".join(i.message for i in issues.errors), fields)
    notes = [] if canonical == text else ["Valid, but not in DocumentLab's exact compact layout (spacing or field order differs)."]
    return Interpretation("documentlab_schema", schema.name, PASS, f"All fields match the {schema.name} schema.", fields, notes)
