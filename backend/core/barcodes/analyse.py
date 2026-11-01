"""Analyses an uploaded file: finds barcodes, judges image quality, checks the data.

Results use the validation statuses shared across DocumentLab:
    PASS, FAIL, REVIEW_REQUIRED, NOT_SUPPORTED, UNAVAILABLE, NOT_CHECKED

The overall result is never better than the weakest barcode. A read that is not
reproducible, a damaged symbol or an identity-document payload is never reported as PASS.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.files import LoadedFile
from core.imaging.quality import assess_barcode, assess_image, tilt_degrees

from . import decode as decoder
from .interpret import interpret

PASS, FAIL, REVIEW, NOT_SUPPORTED, UNAVAILABLE, NOT_CHECKED = (
    "PASS", "FAIL", "REVIEW_REQUIRED", "NOT_SUPPORTED", "UNAVAILABLE", "NOT_CHECKED")
_RANK = {NOT_CHECKED: -1, PASS: 0, NOT_SUPPORTED: 1, REVIEW: 2, UNAVAILABLE: 3, FAIL: 4}


def worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: _RANK[s]) if statuses else NOT_CHECKED


@dataclass
class Check:
    category: str
    status: str
    detail: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class BarcodeResult:
    page: int
    index: int
    format_name: str
    format_key: str | None
    supported: bool
    text: str | None              # None when withheld (identity-document data)
    byte_length: int
    valid: bool
    error: str
    points: list
    tilt: float
    ec_level: str
    symbology_identifier: str
    consistent_reads: int
    attempts: int
    alternatives: dict
    interpretation: dict
    findings: list[dict]
    expected_match: bool | None
    status: str
    reason: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class AnalysisReport:
    status: str
    summary: str
    next_action: str
    checks: list[Check] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    barcodes: list[BarcodeResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sensitive: bool = False
    duration_ms: int = 0
    decoder: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status, "summary": self.summary, "next_action": self.next_action,
                "checks": [c.as_dict() for c in self.checks], "pages": self.pages,
                "barcodes": [b.as_dict() for b in self.barcodes], "warnings": self.warnings,
                "sensitive": self.sensitive, "duration_ms": self.duration_ms, "decoder": self.decoder}


def _matches(expected: str, read: decoder.Read) -> bool:
    candidates = {read.text, *read.alternatives.values()}
    if read.format_key == "upca" or (read.format_name == "EAN-13" and read.text.startswith("0")):
        candidates.add(read.text[1:])  # UPC-A is reported by decoders with a leading 0
    return expected in candidates


def _judge(read: decoder.Read, meaning, expected: str | None) -> tuple[str, str, bool | None]:
    """Status and reason for one barcode."""
    if meaning.sensitive:
        # No comparison at all: answering "matches / doesn't match" would reveal withheld content.
        return REVIEW, meaning.data_detail, None
    match = None if not expected else _matches(expected, read)
    if not read.valid:
        return FAIL, f"Found, but it couldn't be decoded ({read.error or 'damaged or incomplete'}).", match
    if not read.supported:
        return NOT_SUPPORTED, f"{read.format_name} is read but not one of the formats DocumentLab analyses.", match
    if meaning.data_check == FAIL:
        return FAIL, meaning.data_detail, match
    if match is False:
        return FAIL, "The decoded value doesn't match the expected value.", match
    if read.consistent_reads < read.attempts:
        return REVIEW, (f"Read the same way in only {read.consistent_reads} of {read.attempts} attempts at "
                        "different scales, so the read is fragile."), match
    return PASS, "Decoded, valid and read consistently.", match


def analyse(loaded: LoadedFile, expected: str | None = None, file_warnings: list[str] | None = None) -> AnalysisReport:
    started = time.perf_counter()
    expected = (expected or "").strip() or None
    report = AnalysisReport(NOT_CHECKED, "", "", decoder=decoder.decoder_version())
    report.warnings = list(file_warnings or []) + list(loaded.notes)
    report.checks.append(Check("file_integrity", REVIEW if file_warnings else PASS,
                               file_warnings[0] if file_warnings else
                               f"{loaded.kind.upper()} file opened; {len(loaded.pages)} page(s) analysed."))

    if not decoder.available():
        report.status, report.summary = UNAVAILABLE, "The barcode decoder isn't installed, so nothing was read."
        report.next_action = "Install zxing-cpp (see requirements.txt) and analyse the file again."
        report.checks.append(Check("barcode_decoding", UNAVAILABLE, report.summary))
        return report

    quality_flags = []
    for page in loaded.pages:
        quality = assess_image(page.image)
        report.pages.append({"page": page.number, **quality.as_dict()})
        quality_flags += [f"Page {page.number}: {f.message}" if len(loaded.pages) > 1 else f.message for f in quality.findings]

        for index, read in enumerate(decoder.read_image(page.image), start=1):
            meaning = interpret(read.format_key, read.text, read.raw_bytes) if read.valid else None
            if meaning is None:
                from .interpret import Interpretation
                meaning = Interpretation("unreadable", "Not decoded", NOT_CHECKED, "")
            status, reason, match = _judge(read, meaning, expected)
            report.sensitive |= meaning.sensitive
            report.barcodes.append(BarcodeResult(
                page=page.number, index=index, format_name=read.format_name, format_key=read.format_key,
                supported=read.supported, text=None if meaning.sensitive else read.text,
                byte_length=len(read.raw_bytes), valid=read.valid, error=read.error, points=read.points,
                tilt=round(tilt_degrees(read.points), 1), ec_level=read.ec_level,
                symbology_identifier=read.symbology_identifier, consistent_reads=read.consistent_reads,
                attempts=read.attempts, alternatives={} if meaning.sensitive else read.alternatives,
                interpretation=meaning.as_dict(),
                findings=[f.as_dict() for f in assess_barcode(read.points, page.image.size)],
                expected_match=match, status=status, reason=reason,
            ))

    _summarise(report, quality_flags, expected)
    report.duration_ms = int((time.perf_counter() - started) * 1000)
    return report


def _summarise(report: AnalysisReport, quality_flags: list[str], expected: str | None) -> None:
    codes = report.barcodes
    report.checks.append(Check("image_quality", REVIEW if quality_flags else PASS,
                               " ".join(quality_flags) if quality_flags else "No image-quality problems found."))

    if not codes:
        report.checks.append(Check("barcode_decoding", FAIL, "No barcode could be read."))
        report.checks.append(Check("data_format", NOT_CHECKED, "Nothing was decoded."))
        report.checks.append(Check("expected_value", FAIL if expected else NOT_CHECKED,
                                   "Nothing was decoded to compare." if expected else "No expected value given."))
        report.status, report.summary = FAIL, "No barcode could be read."
        report.next_action = (quality_flags[0] if quality_flags else
                              "Make sure the whole barcode is in the picture and in a supported format, "
                              "then scan again at a higher resolution.")
        return

    decoding = worst(*[FAIL if not b.valid else REVIEW if b.consistent_reads < b.attempts else
                       NOT_SUPPORTED if not b.supported else PASS for b in codes])
    report.checks.append(Check("barcode_decoding", decoding,
                               f"{sum(b.valid for b in codes)} of {len(codes)} barcode(s) decoded."))
    data = worst(*[b.interpretation["data_check"] for b in codes])
    report.checks.append(Check("data_format", data, next(
        (b.interpretation["data_detail"] for b in codes if b.interpretation["data_check"] == data and b.interpretation["data_detail"]),
        "No format rules apply to this data." if data == NOT_CHECKED else "")))
    if expected and report.sensitive:
        report.checks.append(Check("expected_value", NOT_CHECKED,
                                   "Not compared: identity-document data is withheld, so no comparison is made."))
    elif expected:
        matched = any(b.expected_match for b in codes)
        report.checks.append(Check("expected_value", PASS if matched else FAIL,
                                   "A barcode matches the expected value." if matched else
                                   "No barcode matches the expected value."))
        if not matched:
            for b in codes:
                if b.status == PASS:
                    b.status, b.reason = FAIL, "The decoded value doesn't match the expected value."
    else:
        report.checks.append(Check("expected_value", NOT_CHECKED, "No expected value given."))

    report.status = worst(*[b.status for b in codes])
    if report.status == NOT_SUPPORTED and any(b.status == PASS for b in codes):
        report.status = REVIEW

    first_bad = next((b for b in codes if b.status == report.status), codes[0])
    n = len(codes)
    names = ", ".join(sorted({b.format_name for b in codes}))
    if report.status == PASS:
        report.summary = f"{n} barcode{'s' if n > 1 else ''} read and checked ({names})."
        report.next_action = ("No action needed." if not quality_flags else
                              f"The barcode read correctly, but for better scans: {quality_flags[0]}")
    elif report.status == FAIL:
        report.summary = first_bad.reason
        report.next_action = (
            "Rescan the barcode. If it still fails, the printed code may be damaged." if not first_bad.valid else
            "Compare the decoded and expected values; the label may be wrong or swapped."
            if first_bad.expected_match is False else
            "Check how this barcode was created; its data breaks the format's rules.")
    elif report.status == REVIEW:
        report.summary = first_bad.reason
        report.next_action = (
            "Identity documents are handled in Document Analysis (Phase 7), which has stricter access and retention controls."
            if report.sensitive else
            "Rescan straight-on, closer and in good light, then analyse again." if first_bad.consistent_reads < first_bad.attempts else
            "Review the barcodes in formats DocumentLab doesn't analyse; only their raw text is shown.")
    else:
        report.summary = first_bad.reason
        report.next_action = "Only the raw text is shown for this format."
