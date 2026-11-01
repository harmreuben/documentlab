"""Expected results for test fixtures, and how an actual result is compared with them.

An expectation is a small JSON object. Every key is optional; only the keys present are checked.

    status          "PASS", or a list of acceptable results, e.g. ["PASS", "REVIEW_REQUIRED"]
    checks          {key: status or list}. Barcode Analyzer keys are check categories
                    ("image_quality"); Document Analysis keys are check codes ("mrz.check_digit.composite")
                    or categories ("consistency", meaning the worst result in that category)
    max_duration_ms the run may take at most this long (catches performance regressions)

    Barcode Analyzer only:
    barcode_count   exact number of barcodes found
    barcodes        [{"format": "EAN-13", "text": "5901234123457"}]; each must be found ("text" optional)

    Document Analysis only:
    detected_type   "passport", "id_card", "driving_licence", "other" or "unknown"
    fields          {"surname": "ERIKSSON"}; compared with the extracted value, ignoring case and spaces
"""
from __future__ import annotations

from dataclasses import dataclass

STATUSES = {"PASS", "FAIL", "REVIEW_REQUIRED", "NOT_SUPPORTED", "UNAVAILABLE", "NOT_CHECKED"}
_RANK = {"NOT_CHECKED": -1, "PASS": 0, "NOT_SUPPORTED": 1, "REVIEW_REQUIRED": 2, "UNAVAILABLE": 3, "FAIL": 4}
MODULES = {"analyzer": "Barcode Analyzer", "documents": "Document Analysis"}
DOC_TYPES = {"passport", "id_card", "driving_licence", "other", "unknown"}
COMMON_KEYS = {"status", "checks", "max_duration_ms"}
MODULE_KEYS = {"analyzer": {"barcode_count", "barcodes"}, "documents": {"detected_type", "fields"}}


class InvalidExpectation(ValueError):
    pass


def _status_list(value, where: str) -> list[str]:
    values = value if isinstance(value, list) else [value]
    if not values or not all(isinstance(v, str) and v in STATUSES for v in values):
        raise InvalidExpectation(f"{where}: use one or more of {', '.join(sorted(STATUSES))}.")
    return values


def validate(module: str, expected) -> dict:
    """Return a cleaned copy of the expectation, or raise InvalidExpectation with a plain message."""
    if module not in MODULES:
        raise InvalidExpectation("Choose the Barcode Analyzer or Document Analysis.")
    if not isinstance(expected, dict) or not expected:
        raise InvalidExpectation("Give at least one expectation, for example {\"status\": \"PASS\"}.")
    unknown = set(expected) - COMMON_KEYS - MODULE_KEYS[module]
    if unknown:
        raise InvalidExpectation(f"Not used for the {MODULES[module]}: {', '.join(sorted(unknown))}.")
    clean: dict = {}
    if "status" in expected:
        clean["status"] = _status_list(expected["status"], "status")
    if "checks" in expected:
        if not isinstance(expected["checks"], dict) or not expected["checks"]:
            raise InvalidExpectation("checks: give an object such as {\"image_quality\": \"PASS\"}.")
        clean["checks"] = {str(k): _status_list(v, f"checks.{k}") for k, v in expected["checks"].items()}
    if "max_duration_ms" in expected:
        value = expected["max_duration_ms"]
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 600_000:
            raise InvalidExpectation("max_duration_ms: a whole number of milliseconds between 1 and 600000.")
        clean["max_duration_ms"] = value
    if "barcode_count" in expected:
        value = expected["barcode_count"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise InvalidExpectation("barcode_count: a whole number from 0 to 100.")
        clean["barcode_count"] = value
    if "barcodes" in expected:
        items = expected["barcodes"]
        if not isinstance(items, list) or not items or not all(isinstance(i, dict) and isinstance(i.get("format"), str) for i in items):
            raise InvalidExpectation("barcodes: a list such as [{\"format\": \"EAN-13\", \"text\": \"5901234123457\"}].")
        clean["barcodes"] = [{"format": i["format"], **({"text": str(i["text"])} if "text" in i else {})} for i in items]
    if "detected_type" in expected:
        if expected["detected_type"] not in DOC_TYPES:
            raise InvalidExpectation(f"detected_type: one of {', '.join(sorted(DOC_TYPES))}.")
        clean["detected_type"] = expected["detected_type"]
    if "fields" in expected:
        if not isinstance(expected["fields"], dict) or not expected["fields"]:
            raise InvalidExpectation("fields: an object such as {\"surname\": \"ERIKSSON\"}.")
        clean["fields"] = {str(k): str(v) for k, v in expected["fields"].items()}
    return clean


# --- The actual result, reduced to what expectations can refer to -------------------------------

def summarise(module: str, report: dict) -> dict:
    """A compact copy of a report: enough to compare and to show, nothing more."""
    actual = {"status": report["status"], "summary": report["summary"], "duration_ms": report.get("duration_ms", 0)}
    if module == "analyzer":
        actual["checks"] = {c["category"]: c["status"] for c in report["checks"]}
        actual["barcodes"] = [{"format": b["format_name"], "text": b["text"], "status": b["status"]} for b in report["barcodes"]]
        actual["barcode_count"] = len(report["barcodes"])
    else:
        checks: dict = {}
        for c in report["checks"]:
            checks[c["code"]] = c["status"]
            checks[c["category"]] = max(checks.get(c["category"], "NOT_CHECKED"), c["status"], key=_RANK.__getitem__)
        actual["checks"] = checks
        actual["detected_type"] = report["detected_type"]
        actual["fields"] = {k: v.get("value", "") for k, v in report["fields"].items()}
    return actual


@dataclass
class Comparison:
    label: str
    expected: str
    actual: str
    passed: bool

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _norm(value) -> str:
    return "".join(str(value or "").upper().split())


def _either(values: list[str]) -> str:
    return " or ".join(values)


def evaluate(module: str, expected: dict, actual: dict) -> list[Comparison]:
    """Compare each expectation with the actual result. Every expectation produces one row."""
    rows: list[Comparison] = []
    if "status" in expected:
        rows.append(Comparison("Overall result", _either(expected["status"]), actual["status"],
                               actual["status"] in expected["status"]))
    for key, wanted in expected.get("checks", {}).items():
        got = actual["checks"].get(key)
        rows.append(Comparison(f"Check: {key}", _either(wanted), got or "not run", got in wanted))
    if "barcode_count" in expected:
        rows.append(Comparison("Barcodes found", str(expected["barcode_count"]), str(actual["barcode_count"]),
                               actual["barcode_count"] == expected["barcode_count"]))
    for want in expected.get("barcodes", []):
        same_format = [b for b in actual["barcodes"] if b["format"] == want["format"]]
        label = f"{want['format']}" + (f" reading \"{want['text']}\"" if "text" in want else "")
        if "text" in want:
            hit = any(b["text"] == want["text"] for b in same_format)
            got = "; ".join(f"\"{b['text']}\"" if b["text"] is not None else "(withheld)" for b in same_format) or "not found"
        else:
            hit, got = bool(same_format), f"{len(same_format)} found"
        rows.append(Comparison(f"Barcode: {label}", "found", "found" if hit else got, hit))
    if "detected_type" in expected:
        rows.append(Comparison("Document type", expected["detected_type"], actual["detected_type"],
                               actual["detected_type"] == expected["detected_type"]))
    for key, value in expected.get("fields", {}).items():
        got = actual["fields"].get(key)
        rows.append(Comparison(f"Field: {key}", value, got if got is not None else "not extracted",
                               got is not None and _norm(got) == _norm(value)))
    if "max_duration_ms" in expected:
        rows.append(Comparison("Time taken", f"at most {expected['max_duration_ms']} ms", f"{actual['duration_ms']} ms",
                               actual["duration_ms"] <= expected["max_duration_ms"]))
    return rows


def from_actual(module: str, actual: dict) -> dict:
    """An expectation that matches this result exactly (used when a person adopts a reviewed result)."""
    expected: dict = {"status": [actual["status"]]}
    if module == "analyzer":
        expected["barcode_count"] = actual["barcode_count"]
        codes = [{"format": b["format"], **({"text": b["text"]} if b["text"] is not None else {})} for b in actual["barcodes"]]
        if codes:
            expected["barcodes"] = codes
    else:
        expected["detected_type"] = actual["detected_type"]
        picked = {k: v for k, v in actual["fields"].items() if k in ("surname", "given_names", "document_number", "birth_date") and v}
        if picked:
            expected["fields"] = picked
        mrz_checks = {k: [v] for k, v in actual["checks"].items() if k.startswith("mrz.check_digit")}
        if mrz_checks:
            expected["checks"] = mrz_checks
    return expected
