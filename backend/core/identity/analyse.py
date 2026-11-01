"""Analyses an identity document: OCR, MRZ, licence barcode, dates and printed-versus-encoded consistency.

The overall status describes the technical checks only. Authenticity is always reported
as not checked: DocumentLab can't tell whether a document is genuine.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from core.barcodes import decode as barcode_decoder
from core.barcodes.guards import identity_layout_reason
from core.files import LoadedFile
from core.imaging.quality import assess_image
from core.ocr import engine as ocr

from . import licence, mrz
from .checks import FAIL, NOT_CHECKED, NOT_SUPPORTED, PASS, REVIEW, UNAVAILABLE, Check, worst
from .compare import normalise_name
from .dates import dates_in_text, nice

TYPES = {"auto": "Detect automatically", "passport": "Passport", "id_card": "ID card",
         "driving_licence": "Driving licence", "other": "Other document"}
MIN_WORDS = 5  # fewer recognised words than this = a side with no printed text (e.g. a barcode)
AUTHENTICITY = {"status": NOT_CHECKED,
                "detail": "DocumentLab performs technical checks only. It can't tell whether a document is genuine."}


@dataclass
class DocReport:
    status: str = NOT_CHECKED
    summary: str = ""
    next_action: str = ""
    requested_type: str = "auto"
    detected_type: str = "unknown"
    source: str = "upload"
    checks: list[Check] = field(default_factory=list)
    fields: dict = field(default_factory=dict)
    mrz: dict | None = None
    licence: dict | None = None
    ocr: list[dict] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ocr_engine: str = ""
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return {"status": self.status, "summary": self.summary, "next_action": self.next_action,
                "requested_type": self.requested_type, "detected_type": self.detected_type, "source": self.source,
                "checks": [c.as_dict() for c in self.checks], "fields": self.fields, "mrz": self.mrz,
                "licence": self.licence, "ocr": self.ocr, "pages": self.pages, "warnings": self.warnings,
                "ocr_engine": self.ocr_engine, "authenticity": AUTHENTICITY, "duration_ms": self.duration_ms}


# --- Helpers ---------------------------------------------------------------------------------

def _score(result: mrz.MrzResult) -> tuple[int, int]:
    """Lower is better: (failed checks, corrections)."""
    return (sum(c.status == FAIL for c in result.checks if c.category in ("parsing", "data_format")),
            len(result.corrections))


def _best_mrz(texts: list[str], today: date) -> mrz.MrzResult | None:
    parsed = [mrz.parse(lines, today) for lines in (mrz.find_mrz(t) for t in texts if t) if lines]
    parsed = [p for p in parsed if p is not None]
    return min(parsed, key=_score) if parsed else None


def _visual_text(text: str) -> str:
    """OCR text without the MRZ lines, so the printed part can be compared with the MRZ."""
    return "\n".join(l for l in text.splitlines() if not mrz._looks_like_mrz(mrz.normalise_line(l)))


def _closest(value: str, text: str) -> tuple[float, str]:
    tokens = re.findall(r"[A-Z0-9]+", text.upper())
    best = (0.0, "")
    for token in tokens:
        ratio = SequenceMatcher(None, value.upper(), token).ratio()
        if ratio > best[0]:
            best = (ratio, token)
    return best


def _consistency(report: DocReport, visual: str, source_label: str) -> None:
    """Compare the encoded fields (MRZ or barcode) with the printed text OCR found."""
    if len(visual.split()) < MIN_WORDS:
        report.checks.append(Check("consistency", "consistency.printed_text", "Printed text compared", NOT_CHECKED,
                                   "No printed text was read, so the encoded data couldn't be compared with it."))
        return
    f = report.fields
    norm_visual = f" {normalise_name(visual)} "

    number = (f.get("document_number") or {}).get("value", "")
    if number:
        ratio, token = _closest(number, visual)
        status = PASS if ratio == 1 else REVIEW
        detail = (f"The printed document number matches the {source_label}." if ratio == 1 else
                  f"The closest printed text is '{token}' ({ratio:.0%} similar)." if ratio >= 0.8 else
                  "The document number wasn't found in the printed text (OCR may have missed it).")
        report.checks.append(Check("consistency", "consistency.document_number", f"Document number: printed vs {source_label}",
                                   status, detail))

    for key, label in (("surname", "Surname"), ("given_names", "Given names")):
        name = normalise_name((f.get(key) or {}).get("value", ""))
        if not name:
            continue
        if f" {name} " in norm_visual:
            report.checks.append(Check("consistency", f"consistency.{key}", f"{label}: printed vs {source_label}", PASS,
                                       f"The printed {label.lower()} matches the {source_label}."))
            continue
        words, missing = name.split(), []
        for word in words:
            if f" {word} " not in norm_visual:
                ratio, token = _closest(word, visual)
                missing.append(f"'{word}' (closest printed: '{token}', {ratio:.0%})" if ratio >= 0.6 else f"'{word}'")
        report.checks.append(Check("consistency", f"consistency.{key}", f"{label}: printed vs {source_label}", REVIEW,
                                   f"Not matched exactly in the printed text: {', '.join(missing)}. "
                                   "This is often an OCR misread; compare by eye."))

    born = (f.get("birth_date") or {}).get("value", "")
    printed_dates = dates_in_text(visual)
    if born and printed_dates:
        same = any(d.isoformat() == born for d in printed_dates)
        report.checks.append(Check("consistency", "consistency.birth_date", f"Date of birth: printed vs {source_label}",
                                   PASS if same else REVIEW,
                                   "The printed date of birth matches." if same else
                                   "None of the printed dates match the encoded date of birth."))


def _summarise(report: DocReport) -> None:
    graded = [c for c in report.checks if c.category != "external"]
    report.status = worst(c.status for c in graded)
    kind = TYPES.get(report.detected_type, "document").lower()
    first = next((c for c in graded if c.status == report.status), None)
    if report.status == PASS:
        report.summary = f"Technical checks passed for this {kind}."
        report.next_action = "None. Remember that this does not confirm the document is genuine."
        return
    if report.status in (NOT_CHECKED, NOT_SUPPORTED):
        report.summary = "Only the text could be read; there were no machine-readable fields to check."
        report.next_action = "Review the OCR text. Upload a passport, ID card or licence for field checks."
        return
    if report.status == UNAVAILABLE:
        report.summary = first.detail if first else "A required tool is unavailable."
        report.next_action = "Install Tesseract OCR (see the setup guide), or enter the MRZ by hand."
        return
    lead = "Technical checks found a problem" if report.status == FAIL else "Needs review"
    report.summary = f"{lead}: {first.detail}" if first else lead
    code = first.code if first else ""
    report.next_action = (
        "The document has expired. Ask for a current one." if code.endswith("not_expired") else
        "Re-scan the machine-readable zone more clearly, or type it in by hand, and compare it with the document."
        if code.startswith("mrz.check_digit") and first.status == FAIL else
        "Compare the corrected characters with the document." if code in ("mrz.corrections", "mrz.check_digit.document_number") else
        "Compare the printed details with the encoded data by eye." if code.startswith("consistency") else
        "Re-scan the document flat, in focus and in even light." if code.startswith("quality") or code.startswith("ocr") else
        "Upload a clearer image of the side with the machine-readable zone or barcode." if code.startswith("parsing") else
        "Have a reviewer look at the highlighted checks.")


def _apply_mrz(report: DocReport, result: mrz.MrzResult) -> None:
    report.mrz = result.as_dict()
    report.checks += result.checks
    for key, value in result.fields.items():
        report.fields[key] = {**value, "source": "MRZ"}
    report.detected_type = "passport" if result.layout == "TD3" else "id_card"


def _apply_licence(report: DocReport, payload: str, today: date) -> None:
    result = licence.read(payload, today)
    report.licence = result.as_dict()
    report.checks += result.checks
    for key, value in result.fields.items():
        report.fields.setdefault(key, {**value, "source": "Licence barcode"})
    if report.detected_type == "unknown":
        report.detected_type = "driving_licence"


def _type_check(report: DocReport) -> None:
    requested, detected = report.requested_type, report.detected_type
    if requested in ("auto", "other") or detected == "unknown":
        return
    if requested != detected:
        report.checks.append(Check("parsing", "document.type", "Document type", REVIEW,
                                   f"You chose {TYPES[requested].lower()}, but the data looks like a {TYPES[detected].lower()}."))


# --- Entry points ------------------------------------------------------------------------

def analyse_mrz_text(text: str, requested_type: str = "auto", today: date | None = None) -> DocReport:
    """Check an MRZ typed or pasted by hand (no image, no OCR)."""
    started, today = time.perf_counter(), today or date.today()
    report = DocReport(requested_type=requested_type, source="manual_mrz")
    lines = mrz.find_mrz(text) or [l for l in text.splitlines() if l.strip()]
    result = mrz.parse(lines, today)
    if result is None:
        report.checks.append(Check("parsing", "mrz.found", "Machine-readable zone", FAIL,
                                   "That doesn't look like an MRZ. Enter 2 lines of 44 or 36 characters, or 3 lines of 30."))
    else:
        _apply_mrz(report, result)
        report.checks.append(Check("consistency", "consistency.printed_text", "Printed text compared", NOT_CHECKED,
                                   "Entered by hand, so there is no printed text to compare with."))
    _type_check(report)
    report.checks.append(Check("external", "external.verification", "Issuer verification", UNAVAILABLE,
                               "No authorised verification provider is connected."))
    _summarise(report)
    report.duration_ms = int((time.perf_counter() - started) * 1000)
    return report


def analyse_document(loaded: LoadedFile, requested_type: str = "auto", file_warnings: list[str] | None = None,
                     today: date | None = None) -> DocReport:
    started, today = time.perf_counter(), today or date.today()
    report = DocReport(requested_type=requested_type)
    report.warnings = list(file_warnings or []) + list(loaded.notes)
    report.checks.append(Check("file_integrity", "file.opened", "File", REVIEW if file_warnings else PASS,
                               file_warnings[0] if file_warnings else f"{loaded.kind.upper()} opened; {len(loaded.pages)} page(s) read."))

    ocr_ok, engine = ocr.status()
    report.ocr_engine = engine
    texts, visual, licence_payload = [], [], None
    quality_messages = []
    for page in loaded.pages:
        quality = assess_image(page.image)
        report.pages.append({"page": page.number, **quality.as_dict()})
        quality_messages += [f.message for f in quality.findings]
        if ocr_ok:
            result = ocr.read_page(page.image)
            report.ocr.append({"page": page.number, **result.as_dict()})
            texts += [result.text, ocr.read_mrz_band(page.image)]
            visual.append(_visual_text(result.text))
        for read in barcode_decoder.read_image(page.image):
            # The decoder's display text replaces control characters (e.g. "<RS>"); licence fields need the raw bytes.
            raw = read.raw_bytes.decode("utf-8", errors="replace") if read.raw_bytes else read.text
            if read.valid and licence_payload is None and identity_layout_reason(raw):
                licence_payload = raw

    report.checks.append(Check("image_quality", "quality.image", "Image quality", REVIEW if quality_messages else PASS,
                               " ".join(quality_messages) if quality_messages else "No image-quality problems found."))
    if ocr_ok:
        confidence = min((o["mean_confidence"] for o in report.ocr if o["word_count"]), default=0.0)
        words = sum(o["word_count"] for o in report.ocr)
        report.checks.append(Check("ocr", "ocr.confidence", "Text recognition",
                                   NOT_CHECKED if words < MIN_WORDS else PASS if confidence >= 75 else REVIEW,
                                   "Little or no printed text was found." if words < MIN_WORDS else
                                   f"{words} words read; average confidence {confidence:.0f}%"
                                   + ("." if confidence >= 75 else ". Low-confidence words should be checked.")))
    else:
        report.checks.append(Check("ocr", "ocr.available", "Text recognition", UNAVAILABLE, engine))

    found = _best_mrz(texts, today) if ocr_ok else None
    if found:
        _apply_mrz(report, found)
    if licence_payload:
        _apply_licence(report, licence_payload, today)

    if not found and not licence_payload:
        wants = report.requested_type
        if not ocr_ok and wants != "driving_licence":
            report.checks.append(Check("parsing", "document.fields", "Machine-readable data", UNAVAILABLE,
                                       "Without OCR the machine-readable zone can't be read. Enter it by hand instead."))
        elif wants in ("passport", "id_card"):
            report.checks.append(Check("parsing", "mrz.found", "Machine-readable zone", FAIL,
                                       "No machine-readable zone could be read. Upload a clearer image of the photo page."))
        elif wants == "driving_licence":
            report.checks.append(Check("parsing", "licence.found", "Licence barcode", FAIL,
                                       "No licence barcode could be read. Upload the back of the licence, flat and in focus."))
        else:
            report.checks.append(Check("parsing", "document.fields", "Machine-readable data", NOT_SUPPORTED,
                                       "No MRZ or licence barcode was found, so only the text was read."))
            report.detected_type = "other"
    elif ocr_ok:
        _consistency(report, "\n".join(visual), "MRZ" if found else "barcode")

    _type_check(report)
    report.checks.append(Check("external", "external.verification", "Issuer verification", UNAVAILABLE,
                               "No authorised verification provider is connected."))
    _summarise(report)
    report.duration_ms = int((time.perf_counter() - started) * 1000)
    return report
