"""Every validation rule DocumentLab applies, in one place.

A rule describes a check that already runs in the analysis code: what it looks at, which results it
can give and when, where the rule comes from, and how it has changed. The catalogue documents
behaviour; it does not drive it. A test (tests/test_rules.py) fails if the analysis code emits a check
that isn't catalogued here, so the two can't drift apart.

When a rule's behaviour changes: raise its `version`, add a line to `changes`, and raise
RULESET_VERSION. Every analysis records the RULESET_VERSION it was made under.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch

from core.identity import compare as id_compare
from core.identity.analyse import MIN_WORDS
from core.imaging import quality as q

RULESET_VERSION = "2026.11.2"

PASS, FAIL, REVIEW = "PASS", "FAIL", "REVIEW_REQUIRED"
NOT_SUPPORTED, UNAVAILABLE, NOT_CHECKED = "NOT_SUPPORTED", "UNAVAILABLE", "NOT_CHECKED"

MODULES = {
    "generator": "Barcode Generator",
    "analyzer": "Barcode Analyzer",
    "documents": "Document Analysis",
    "ssn": "SSN format check",
    "comparison": "Document comparison",
}

# Severity = the worst result a rule can give on its own.
SEVERITY = {
    "blocking": "Can fail the result",
    "review": "Can only ask for review",
    "information": "Reports a limitation; never passes or fails",
}

ICAO = "ICAO Doc 9303, Machine Readable Travel Documents"


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    module: str
    category: str
    checks: str                    # what the rule looks at, in plain words
    outcomes: dict                 # status -> when it is given
    reference: str = "DocumentLab"
    version: int = 1
    since: str = "0.7.0"           # DocumentLab version that introduced it
    changes: tuple = ()            # ((version, app_version, what changed), ...)
    parameters: dict = field(default_factory=dict)
    keys: tuple = ()               # check identifiers this rule produces in results (wildcards allowed)
    lab_module: str = ""           # Testing Laboratory module whose results show this rule, if any

    @property
    def severity(self) -> str:
        if FAIL in self.outcomes:
            return "blocking"
        if REVIEW in self.outcomes:
            return "review"
        return "information"

    @property
    def match_keys(self) -> tuple:
        return self.keys or (self.code,)

    def produces(self, key: str) -> bool:
        return any(fnmatch(key, pattern) for pattern in self.match_keys)


def _r(*args, **kwargs) -> Rule:
    return Rule(*args, **kwargs)


RULES: list[Rule] = [
    # --- Barcode Generator ------------------------------------------------------------------------
    _r("generator.identity_guard", "Identity layouts are refused", "generator", "safety",
       "Looks for data laid out like a driver's licence, ID card or passport (for example an AAMVA header) before "
       "drawing a barcode.",
       {FAIL: "The data has an identity-document layout. Nothing is drawn."},
       since="0.5.0"),
    _r("generator.data_rules", "Data fits the barcode format", "generator", "data_format",
       "Checks the characters, length and check digit each format allows (for example EAN-13 takes 12 digits plus "
       "a calculated check digit).",
       {FAIL: "The data breaks the format's rules; the message names the problem.",
        PASS: "The data is allowed."},
       reference="ISO/IEC 15420 (EAN/UPC), ISO/IEC 15417 (Code 128), ISO/IEC 16388 (Code 39), "
                 "ISO/IEC 18004 (QR), ISO/IEC 15438 (PDF417)",
       since="0.5.0"),
    _r("generator.verification", "Independent read-back", "generator", "verification",
       "Decodes every generated image with a separate decoder (zxing-cpp) and compares the result with the data.",
       {PASS: "The image decodes to exactly the intended data.",
        FAIL: "The image doesn't decode, or decodes to something else."},
       since="0.5.0"),

    # --- Barcode Analyzer -------------------------------------------------------------------------
    _r("barcode.file_integrity", "File opens correctly", "analyzer", "file_integrity",
       "Identifies the file by its content (not its name), checks the size limit and opens every page.",
       {PASS: "The file opened.", REVIEW: "It opened with a warning, for example the name doesn't match the content."},
       since="0.6.0", keys=("file_integrity",), lab_module="analyzer",
       parameters={"Largest file": "10 MB", "Largest image": "40 megapixels", "PDF pages read": "10"}),
    _r("barcode.image_quality", "Image quality", "analyzer", "image_quality",
       "Measures resolution, sharpness, contrast and brightness of each page, and the position, size and tilt of "
       "each barcode. Problems are advice: a barcode that still reads correctly can pass.",
       {PASS: "No quality problem found.", REVIEW: "One or more measurements are outside the limits below."},
       since="0.6.0", version=4, keys=("image_quality",), lab_module="analyzer",
       changes=((2, "0.6.0", "Glare detection removed: it mistook white label backgrounds for glare."),
                (3, "0.7.0", "Contrast measured between the 1st and 99th brightness percentiles, so a few dark "
                             "pixels on a light page no longer count as good contrast."),
                (4, "0.10.0", "Blank pages are reported as blank instead of blurred.")),
       parameters={"Smallest long side": f"{q.MIN_LONG_SIDE_PX} px", "Smallest short side": f"{q.MIN_SHORT_SIDE_PX} px",
                   "Lowest sharpness": f"{q.BLUR_SHARPNESS_MIN:g} (Laplacian variance at 1000 px)",
                   "Lowest contrast range": f"{q.CONTRAST_RANGE_MIN:g}", "Darkest average brightness": f"{q.DARK_MEAN_MAX:g}",
                   "Distance from the edge": f"{q.EDGE_MARGIN_MIN_PX} px", "Tilt reported beyond": f"{q.SKEW_TOLERANCE_DEG}°",
                   "Blank page below contrast range": f"{q.BLANK_RANGE_MAX:g}"}),
    _r("barcode.decoding", "Barcodes decode consistently", "analyzer", "barcode_decoding",
       "Reads the page at its own size and at 0.75× and 1.5×. A barcode must decode the same way every time.",
       {PASS: "Every barcode decoded the same way at every scale.",
        REVIEW: "A barcode read differently at different scales, so the read is fragile.",
        FAIL: "No barcode found, or one was found but couldn't be decoded.",
        NOT_SUPPORTED: "A barcode was read in a format DocumentLab doesn't analyse."},
       since="0.6.0", keys=("barcode_decoding",), lab_module="analyzer"),
    _r("barcode.data_format", "Decoded data follows its format", "analyzer", "data_format",
       "Recalculates check digits (EAN, UPC) and validates DocumentLab payload schemas field by field.",
       {PASS: "The check digit or schema is correct.", FAIL: "Wrong check digit, or fields that break the schema.",
        NOT_CHECKED: "Plain text, web addresses and other data have no format to check."},
       reference="GS1 General Specifications (check digit calculation)", since="0.6.0",
       keys=("data_format",), lab_module="analyzer"),
    _r("barcode.expected_value", "Matches the expected value", "analyzer", "expected_value",
       "Compares the decoded data with the value the person said to expect. Identity-document data is never "
       "compared, because a yes/no answer would reveal it.",
       {PASS: "A barcode matches.", FAIL: "No barcode matches.", NOT_CHECKED: "No expected value given, or identity data."},
       since="0.6.0", version=2, keys=("expected_value",), lab_module="analyzer",
       changes=((2, "0.6.0", "Identity-document data is no longer compared with the expected value."),)),

    # --- Document Analysis: file, image, OCR ------------------------------------------------------
    _r("file.opened", "File opens correctly", "documents", "file_integrity",
       "Identifies the file by its content, checks the size limit and opens every page.",
       {PASS: "The file opened.", REVIEW: "It opened with a warning."}, lab_module="documents"),
    _r("quality.image", "Image quality", "documents", "image_quality",
       "The same page measurements as the Barcode Analyzer: resolution, sharpness, contrast and brightness.",
       {PASS: "No problem found.", REVIEW: "A measurement is outside its limit."}, lab_module="documents",
       parameters={"Lowest sharpness": f"{q.BLUR_SHARPNESS_MIN:g}", "Lowest contrast range": f"{q.CONTRAST_RANGE_MIN:g}"}),
    _r("ocr.available", "Text recognition is installed", "documents", "ocr",
       "Checks that Tesseract OCR can be found on this computer.",
       {UNAVAILABLE: "Tesseract isn't installed or can't be found, so images can't be read."}, lab_module="documents"),
    _r("ocr.confidence", "Text recognition confidence", "documents", "ocr",
       "Averages Tesseract's confidence over the recognised words. Pages are enlarged to at least 1800 px wide first.",
       {PASS: "Average confidence is 75% or more.", REVIEW: "Average confidence is below 75%.",
        NOT_CHECKED: f"Fewer than {MIN_WORDS} words found, for example the barcode side of a card."},
       lab_module="documents", parameters={"Lowest average confidence": "75%", "Fewest words to judge": str(MIN_WORDS)}),

    # --- Document Analysis: reading the data --------------------------------------------------------
    _r("mrz.found", "Machine-readable zone found", "documents", "parsing",
       "Looks for 2 lines of 44 or 36 characters, or 3 lines of 30, made of A–Z, 0–9 and <.",
       {FAIL: "Typed text isn't an MRZ."}, reference=ICAO, lab_module="documents"),
    _r("mrz.line_length", "Line lengths", "documents", "parsing",
       "Checks that each line has the length its layout (TD1, TD2 or TD3) requires.",
       {PASS: "Every line has the right length.", FAIL: "A data line is too short or too long."},
       reference=ICAO + ", Parts 4–6", lab_module="documents"),
    _r("mrz.characters", "Allowed characters", "documents", "parsing",
       "Only A–Z, 0–9 and the filler < may appear.",
       {PASS: "Only allowed characters.", FAIL: "Other characters remain after correction."},
       reference=ICAO + ", Part 3", lab_module="documents"),
    _r("mrz.corrections", "Character corrections", "documents", "parsing",
       "OCR confuses letters and digits (O/0, I/1, S/5, B/8). Where a field may only hold digits or only letters, "
       "the character is corrected. Each correction is shown on the result.",
       {PASS: "Every correction is confirmed by a passing check digit.",
        REVIEW: "A correction can't be confirmed by a check digit (names, country codes)."},
       reference=ICAO + ", Part 3", version=2, lab_module="documents",
       changes=((2, "0.7.0", "Corrections confirmed by a passing check digit no longer need review. For the document "
                             "number, the fewest swaps that satisfy the composite check digit are used."),)),
    _r("mrz.document_type", "Document type code", "documents", "parsing",
       "The first character must match the layout: P for passports (TD3), I, A or C for ID cards (TD1, TD2).",
       {REVIEW: "The code doesn't match the layout."}, reference=ICAO, lab_module="documents"),
    _r("mrz.check_digit.*", "Check digits", "documents", "data_format",
       "Recalculates each check digit with weights 7, 3, 1: document number, date of birth, date of expiry, "
       "optional data (TD3) and the composite digit over all of them.",
       {PASS: "The digit matches.", FAIL: "The digit doesn't match: a character was misread or changed."},
       reference=ICAO + ", Part 3, section 4.9", lab_module="documents",
       keys=("mrz.check_digit.document_number", "mrz.check_digit.birth_date", "mrz.check_digit.expiry_date",
             "mrz.check_digit.optional_data", "mrz.check_digit.composite")),
    _r("mrz.sex", "Sex code", "documents", "data_format", "Must be M, F, X or <.",
       {PASS: "Valid code.", FAIL: "Any other character."}, reference=ICAO, lab_module="documents"),
    _r("mrz.state_codes", "Country codes", "documents", "data_format",
       "Issuing state and nationality must be three letters (fillers allowed). UTO, ICAO's fictional specimen "
       "state, is accepted and labelled as a specimen.",
       {PASS: "Three-letter codes.", FAIL: "Digits or other characters."},
       reference=ICAO + ", Part 3, Appendix (ISO 3166-1 alpha-3 codes)", lab_module="documents"),
    _r("mrz.surname_present", "Surname present", "documents", "data_format", "The name field must start with a surname.",
       {PASS: "Present.", FAIL: "Empty."}, reference=ICAO, lab_module="documents"),
    _r("mrz.name_truncated", "Name fits the field", "documents", "data_format",
       "A name that fills the whole field may have been shortened by the issuer.",
       {REVIEW: "The name reaches the end of the field; compare it with the printed name."},
       reference=ICAO + ", Part 3, section 4.6", lab_module="documents"),

    # --- Document Analysis: dates ---------------------------------------------------------------
    _r("mrz.birth_date.valid", "Date of birth is a real past date", "documents", "dates",
       "Reads YYMMDD, chooses the century that puts the date in the past, and checks the date exists.",
       {PASS: "A real date in the past.", FAIL: "Not a real date, or in the future."}, reference=ICAO, lab_module="documents"),
    _r("mrz.expiry_date.valid", "Date of expiry is a real date", "documents", "dates", "Checks the expiry date exists.",
       {FAIL: "Not a real date."}, reference=ICAO, lab_module="documents"),
    _r("mrz.expiry_after_birth", "Expiry is after birth", "documents", "dates", "The expiry date must come after the birth date.",
       {FAIL: "Expiry is on or before birth."}, lab_module="documents"),
    _r("mrz.not_expired", "Document has not expired", "documents", "dates", "Compares the expiry date with today.",
       {PASS: "Valid on or after today.", FAIL: "Expired."}, lab_module="documents"),
    _r("licence.birth_in_past", "Licence date of birth is in the past", "documents", "dates",
       "Reads the licence's date of birth (MMDDCCYY or CCYYMMDD) and checks it is a real past date.",
       {PASS: "A real past date.", FAIL: "Not a real date, or in the future."}, lab_module="documents"),
    _r("licence.not_expired", "Licence has not expired", "documents", "dates", "Compares the licence's expiry date with today.",
       {PASS: "Not expired.", FAIL: "Expired."}, lab_module="documents"),

    # --- Document Analysis: licence barcodes ------------------------------------------------------
    _r("licence.found", "Licence data found", "documents", "parsing",
       "Detects licence data in a PDF417 barcode. DocumentLab reads a few fields for comparison only.",
       {PASS: "Licence data found.", FAIL: "No readable licence data."}, lab_module="documents"),
    _r("licence.fields", "Licence fields read", "documents", "parsing",
       "Reads document number, names, dates and sex, ignoring placeholder values such as NONE.",
       {PASS: "The fields were read.", REVIEW: "Some fields are missing."}, lab_module="documents"),
    _r("licence.field_format", "Licence field formats", "documents", "data_format",
       "Checks the format of each field that was read (dates are real dates, sex is a known code).",
       {PASS: "Valid format.", FAIL: "Invalid value."}, lab_module="documents", keys=("licence.*.valid",)),
    _r("licence.jurisdiction_rules", "Jurisdiction-specific rules", "documents", "external",
       "Each issuing jurisdiction has its own rules. DocumentLab doesn't hold them; they need an authorised provider.",
       {UNAVAILABLE: "Always: not checked by DocumentLab."}, lab_module="documents"),

    # --- Document Analysis: overall -------------------------------------------------------------
    _r("document.type", "Document type matches", "documents", "parsing",
       "Compares the detected document type with the type the person chose.",
       {PASS: "They match, or detection was automatic.", REVIEW: "They differ."}, lab_module="documents"),
    _r("document.fields", "Data found to check", "documents", "parsing",
       "A document needs an MRZ or licence data before anything else can be checked.",
       {NOT_SUPPORTED: "Neither was found, for example an ordinary letter."}, lab_module="documents"),
    _r("consistency.printed_text", "Printed text compared", "documents", "consistency",
       "Whether a printed-versus-encoded comparison was possible.",
       {NOT_CHECKED: "Entered by hand, or too little printed text was read."}, lab_module="documents"),
    _r("consistency.fields", "Printed text matches encoded data", "documents", "consistency",
       "Finds the document number, names and date of birth in the printed text and compares them with the MRZ "
       "or licence data. Names allow for accents and line breaks.",
       {PASS: "Found and the same.", REVIEW: "Not found, or nearly the same.", FAIL: "Clearly different."},
       lab_module="documents",
       keys=("consistency.document_number", "consistency.surname", "consistency.given_names", "consistency.birth_date")),
    _r("external.verification", "Issuer verification", "documents", "external",
       "Whether the issuer confirms the document. Needs an authorised verification provider.",
       {UNAVAILABLE: "No provider is connected."}, lab_module="documents"),
    _r("authenticity", "Authenticity", "documents", "external",
       "Whether the document is genuine. DocumentLab performs technical checks only and never asserts authenticity.",
       {NOT_CHECKED: "Always."}),

    # --- SSN format check -------------------------------------------------------------------------
    _r("ssn.shape", "Nine digits as AAA-GG-SSSS", "ssn", "data_format",
       "Nine digits, with the same separator (dash, space or none) in both places.",
       {PASS: "Correct shape.", FAIL: "Wrong length, characters or separators."},
       reference="Social Security Administration numbering rules"),
    _r("ssn.area", "Area number", "ssn", "data_format", "The first three digits can't be 000, 666 or 900–999.",
       {PASS: "Allowed.", FAIL: "Never issued."}, reference="Social Security Administration numbering rules"),
    _r("ssn.group", "Group number", "ssn", "data_format", "The middle two digits can't be 00.",
       {PASS: "Allowed.", FAIL: "Never issued."}, reference="Social Security Administration numbering rules"),
    _r("ssn.serial", "Serial number", "ssn", "data_format", "The last four digits can't be 0000.",
       {PASS: "Allowed.", FAIL: "Never issued."}, reference="Social Security Administration numbering rules"),
    _r("ssn.published", "Published example numbers", "ssn", "data_format",
       "Numbers published in advertising or examples, and therefore invalid or never used, are flagged.",
       {PASS: "Not a known example.", FAIL: "A number published as invalid.", REVIEW: "A well-known placeholder (123-45-6789)."},
       reference="Social Security Administration"),
    _r("ssn.provider_match", "Provider confirms the details", "ssn", "external",
       "Asks an authorised verification provider whether the number, name and date of birth match its records. Only "
       "runs when a provider is configured and the person's signed consent is recorded.",
       {PASS: "The provider's records match. This confirms the combination, not who is presenting it.",
        FAIL: "The provider's records don't match; the result names the fields.",
        UNAVAILABLE: "No provider is configured, or it didn't answer clearly in time."},
       reference="The provider's own rules (for example SSA eCBSV, restricted to eligible organisations)",
       since="0.10.0"),
    _r("ssn.external", "Issued to this person", "ssn", "external",
       "Whether the number was issued to the person presenting it. Only an authorised verification service can say.",
       {UNAVAILABLE: "No authorised verification service is connected."},
       reference="SSA eCBSV / SSNVS (restricted to eligible organisations)"),

    # --- Comparing documents ------------------------------------------------------------------------
    _r("compare.fields", "Same details across documents", "comparison", "consistency",
       "Compares surname, given names, birth date and sex across 2–4 documents; document number and expiry only "
       "between documents of the same type. Names ignore accents and case.",
       {PASS: "The same.", REVIEW: f"Nearly the same (similarity of {id_compare.NEAR:.0%} or more, or one is the start of the other).",
        FAIL: "Different.", NOT_CHECKED: "Missing on a document, or different document types."},
       parameters={"Near match from": f"{id_compare.NEAR:.0%}"}, keys=tuple(f"compare.{f[0]}" for f in id_compare.FIELDS)),
]

BY_CODE = {r.code: r for r in RULES}


def rule_for(key: str, module: str | None = None) -> Rule | None:
    """The rule that produces this check identifier."""
    for rule in RULES:
        if (module is None or rule.module == module or rule.lab_module == module) and rule.produces(key):
            return rule
    return None
