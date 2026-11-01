"""Runs one test input through the real analysis code and compares the outcome with the expectation.

Nothing here saves analysis records: a test run measures DocumentLab's behaviour, it doesn't add
documents to anyone's history.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

from core.barcodes import analyse as barcode_analysis
from core.files import FileRejected, check_upload, load_pages
from core.identity import analyse as document_analysis

from . import expect

SPECIMEN_STATE = "UTO"  # ICAO's fictional "Utopia", used on specimen documents
PASS, FAIL, ERROR = "PASS", "FAIL", "ERROR"


@dataclass
class FixtureInput:
    module: str                 # "analyzer" or "documents"
    name: str = ""              # file name, for file inputs
    data: bytes | None = None   # file contents
    mrz_text: str = ""          # typed MRZ (documents only)
    options: dict = field(default_factory=dict)  # {"expected_value": ...} or {"document_type": ...}


@dataclass
class CaseOutcome:
    outcome: str                 # PASS, FAIL or ERROR
    actual: dict | None
    comparisons: list[dict]
    error: str = ""
    duration_ms: int = 0


def analyse(item: FixtureInput) -> dict:
    """The full report the module produces for this input."""
    if item.module == "documents" and item.mrz_text:
        return document_analysis.analyse_mrz_text(item.mrz_text, item.options.get("document_type", "auto")).as_dict()
    kind, warnings = check_upload(item.name, item.data or b"")
    loaded = load_pages(kind, item.data)
    if item.module == "analyzer":
        return barcode_analysis.analyse(loaded, item.options.get("expected_value") or None, warnings).as_dict()
    return document_analysis.analyse_document(loaded, item.options.get("document_type", "auto"), warnings).as_dict()


def not_synthetic(module: str, report: dict) -> str | None:
    """Why this input can't be a test fixture, or None. Fixtures must be invented data only."""
    if module == "analyzer":
        if report.get("sensitive"):
            return ("This file holds identity-document data. Test fixtures must be synthetic, so identity barcodes "
                    "can't be added here.")
        return None
    if report.get("licence") or report.get("detected_type") == "driving_licence":
        return ("Licence data can't be confirmed as synthetic, so it can't be used as a fixture. "
                "Use the ICAO specimen documents (state UTO) instead.")
    states = {(report.get("fields", {}).get(k) or {}).get("value", "") for k in ("issuing_state", "nationality")} - {""}
    if states and states != {SPECIMEN_STATE}:
        return (f"Test fixtures must use ICAO's fictional specimen state {SPECIMEN_STATE}. "
                f"This document shows {', '.join(sorted(states))}, so it may be a real person's document.")
    return None


def run(item: FixtureInput, expected: dict) -> CaseOutcome:
    started = time.perf_counter()
    try:
        report = analyse(item)
    except FileRejected as rejected:
        return CaseOutcome(ERROR, None, [], f"The fixture file was rejected: {rejected}",
                           int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001 - one broken fixture must not stop the run
        detail = traceback.format_exception_only(type(exc), exc)[-1].strip()
        return CaseOutcome(ERROR, None, [], f"The analysis stopped with an error: {detail}",
                           int((time.perf_counter() - started) * 1000))
    actual = expect.summarise(item.module, report)
    rows = [r.as_dict() for r in expect.evaluate(item.module, expected, actual)]
    outcome = PASS if rows and all(r["passed"] for r in rows) else FAIL
    return CaseOutcome(outcome, actual, rows, "", int((time.perf_counter() - started) * 1000))
