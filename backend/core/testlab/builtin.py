"""The standard fixture set: synthetic inputs with results decided in advance.

Each fixture's expectation states what DocumentLab *should* do with that input, not whatever it
happens to do today, so a change in behaviour shows up as a failing test.

Inputs are generated, never collected: barcodes come from the Barcode Generator's own engine and
documents are ICAO's fictional "Utopia" specimens. No licence barcodes are included, because the
lab must not become a source of licence-format images.
"""
from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field

from PIL import Image, ImageEnhance, ImageFilter

from core.barcodes import generate

from . import specimens


@dataclass(frozen=True)
class Builtin:
    key: str
    name: str
    module: str
    description: str
    expected: dict
    tags: tuple[str, ...] = ()
    make: Callable[[], tuple[str, bytes]] | None = None   # -> (file name, bytes)
    mrz_text: str = ""
    options: dict = field(default_factory=dict)


# --- Image helpers -------------------------------------------------------------------------------

def _code(fmt: str, data: str, **options) -> Image.Image:
    result = generate(fmt, data, options)
    if result.output is None:
        raise RuntimeError(f"The generator couldn't draw the {fmt} fixture.")
    return Image.open(io.BytesIO(result.output.png)).convert("RGB")


def _canvas(*images: Image.Image, size=(1200, 800)) -> Image.Image:
    canvas = Image.new("RGB", size, "white")
    x = 60
    for im in images:
        canvas.paste(im, (x, 120))
        x += im.width + 80
    return canvas


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def _pdf(images: list[Image.Image], blank_first: bool) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    if blank_first:
        doc.new_page()
    for im in images:
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(72, 72, 72 + im.width * 0.6, 72 + im.height * 0.6), stream=_png(im))
    return doc.tobytes()


def _rotated(image: Image.Image, degrees: float) -> Image.Image:
    return _canvas(image).rotate(degrees, expand=True, fillcolor="white")


EAN = "5901234123457"
QR_TEXT = "https://example.com/documentlab/test"

# --- The set -------------------------------------------------------------------------------------

BUILTINS: list[Builtin] = [
    # Barcode Analyzer: clean inputs
    Builtin("bc-ean13-clean", "EAN-13, clean", "analyzer", "A sharp EAN-13 on a white page, with the expected value given.",
            {"status": ["PASS"], "barcode_count": 1, "barcodes": [{"format": "EAN-13", "text": EAN}],
             "checks": {"expected_value": ["PASS"]}},
            ("clean", "linear"), lambda: ("ean13-clean.png", _png(_canvas(_code("ean13", EAN[:12])))),
            options={"expected_value": EAN}),
    Builtin("bc-qr-clean", "QR Code, clean", "analyzer", "A web address in a QR Code.",
            {"status": ["PASS"], "barcode_count": 1, "barcodes": [{"format": "QR Code", "text": QR_TEXT}]},
            ("clean", "2d"), lambda: ("qr-clean.png", _png(_canvas(_code("qr", QR_TEXT))))),
    Builtin("bc-code128-clean", "Code 128, clean", "analyzer", "Keyboard text in Code 128, saved as JPEG.",
            {"status": ["PASS"], "barcode_count": 1, "barcodes": [{"format": "Code 128", "text": "LAB-TEST-0042"}]},
            ("clean", "linear", "jpeg"), lambda: ("code128.jpg", _jpeg(_canvas(_code("code128", "LAB-TEST-0042"))))),
    Builtin("bc-upca-clean", "UPC-A, clean", "analyzer", "A UPC-A, which decoders report with a leading zero.",
            {"status": ["PASS"], "barcode_count": 1}, ("clean", "linear"),
            lambda: ("upca.png", _png(_canvas(_code("upca", "03600029145"))))),
    Builtin("bc-two-codes", "Two barcodes on one page", "analyzer", "An EAN-13 and a QR Code side by side; both must be found.",
            {"status": ["PASS"], "barcode_count": 2,
             "barcodes": [{"format": "EAN-13", "text": EAN}, {"format": "QR Code", "text": QR_TEXT}]},
            ("clean", "multiple"), lambda: ("two-codes.png", _png(_canvas(_code("ean13", EAN[:12]), _code("qr", QR_TEXT))))),
    Builtin("bc-pdf-page2", "Barcode on page 2 of a PDF", "analyzer", "Page 1 is blank; the barcode is on page 2.",
            {"status": ["PASS"], "barcode_count": 1, "barcodes": [{"format": "Code 128", "text": "PDF-PAGE-TWO"}]},
            ("pdf",), lambda: ("page-two.pdf", _pdf([_canvas(_code("code128", "PDF-PAGE-TWO"))], blank_first=True))),
    Builtin("bc-rotated", "QR Code rotated 20°", "analyzer", "A QR Code photographed at an angle should still be read.",
            {"status": ["PASS", "REVIEW_REQUIRED"], "barcode_count": 1, "barcodes": [{"format": "QR Code", "text": QR_TEXT}]},
            ("degraded", "2d"), lambda: ("qr-rotated.png", _png(_rotated(_code("qr", QR_TEXT), 20)))),
    # Barcode Analyzer: inputs that must not pass
    Builtin("bc-wrong-expected", "Expected value doesn't match", "analyzer",
            "The barcode reads correctly but the expected value is different, so the result must be a failure.",
            {"status": ["FAIL"], "checks": {"expected_value": ["FAIL"]}},
            ("negative",), lambda: ("ean13-mismatch.png", _png(_canvas(_code("ean13", EAN[:12])))),
            options={"expected_value": "4006381333931"}),
    Builtin("bc-blurred", "Heavily blurred barcode", "analyzer", "Too blurred to read. Must never be reported as a pass.",
            {"status": ["FAIL", "REVIEW_REQUIRED"], "checks": {"image_quality": ["REVIEW_REQUIRED", "FAIL"]}},
            ("negative", "degraded"),
            lambda: ("blurred.png", _png(_canvas(_code("ean13", EAN[:12])).filter(ImageFilter.GaussianBlur(6))))),
    Builtin("bc-low-contrast", "Very low contrast", "analyzer",
            "Grey on grey but still readable: the value must be right, and the image-quality check must flag the contrast.",
            {"barcodes": [{"format": "EAN-13", "text": EAN}], "checks": {"image_quality": ["REVIEW_REQUIRED", "FAIL"]}},
            ("degraded",),
            lambda: ("low-contrast.png", _png(ImageEnhance.Contrast(_canvas(_code("ean13", EAN[:12]))).enhance(0.12)))),
    Builtin("bc-blank", "No barcode at all", "analyzer", "A blank page: nothing found, and not a pass.",
            {"status": ["FAIL", "NOT_SUPPORTED", "REVIEW_REQUIRED"], "barcode_count": 0},
            ("negative",), lambda: ("blank.png", _png(Image.new("RGB", (900, 600), "white")))),

    # Document Analysis: typed machine-readable zones
    Builtin("doc-td3-valid", "Passport MRZ, valid specimen", "documents", "ICAO's TD3 specimen with its expiry moved to 2031.",
            {"status": ["PASS"], "detected_type": "passport",
             "fields": {"surname": "ERIKSSON", "given_names": "ANNA MARIA", "document_number": "L898902C3"},
             "checks": {"mrz.check_digit.composite": ["PASS"], "mrz.not_expired": ["PASS"]}},
            ("mrz", "typed"), mrz_text="\n".join(specimens.TD3_VALID)),
    Builtin("doc-td3-expired", "Passport MRZ, expired", "documents", "ICAO's original TD3 specimen, which expired in 2012.",
            {"status": ["FAIL"], "checks": {"mrz.not_expired": ["FAIL"], "mrz.check_digit.composite": ["PASS"]}},
            ("mrz", "typed", "negative"), mrz_text="\n".join(specimens.TD3)),
    Builtin("doc-td3-bad-digit", "Passport MRZ, wrong check digit", "documents",
            "The document-number check digit is changed from 6 to 5. Must fail.",
            {"status": ["FAIL"], "checks": {"mrz.check_digit.document_number": ["FAIL"]}},
            ("mrz", "typed", "negative"),
            mrz_text=specimens.TD3_VALID[0] + "\n" + specimens.TD3_VALID[1][:9] + "5" + specimens.TD3_VALID[1][10:]),
    Builtin("doc-td2-specimen", "ID card MRZ (TD2), expired specimen", "documents", "ICAO's TD2 specimen; the layout must be read.",
            {"status": ["FAIL"], "detected_type": "id_card", "fields": {"document_number": "D23145890"},
             "checks": {"mrz.check_digit.document_number": ["PASS"], "mrz.not_expired": ["FAIL"]}},
            ("mrz", "typed"), mrz_text="\n".join(specimens.TD2)),
    Builtin("doc-td1-specimen", "ID card MRZ (TD1), expired specimen", "documents", "ICAO's three-line TD1 specimen.",
            {"status": ["FAIL"], "detected_type": "id_card", "fields": {"surname": "ERIKSSON"},
             "checks": {"mrz.check_digit.composite": ["PASS"], "mrz.not_expired": ["FAIL"]}},
            ("mrz", "typed"), mrz_text="\n".join(specimens.TD1)),
    Builtin("doc-not-mrz", "Text that isn't an MRZ", "documents", "Ordinary text typed into the MRZ box must be rejected.",
            {"status": ["FAIL"], "checks": {"mrz.found": ["FAIL"]}},
            ("typed", "negative"), mrz_text="HELLO WORLD\nTHIS IS NOT A MACHINE READABLE ZONE"),

    # Document Analysis: images (need OCR)
    Builtin("doc-passport-image", "Passport specimen image", "documents",
            "A sharp specimen data page. OCR must find the MRZ, and every check digit must pass.",
            {"status": ["PASS", "REVIEW_REQUIRED"], "detected_type": "passport",
             "fields": {"surname": "ERIKSSON", "document_number": "L898902C3"},
             "checks": {"mrz.check_digit.composite": ["PASS"], "consistency": ["PASS", "REVIEW_REQUIRED"]}},
            ("image", "ocr"), lambda: ("passport-specimen.png", _png(specimens.passport_image()))),
    Builtin("doc-printed-mismatch", "Printed number differs from MRZ", "documents",
            "The printed passport number doesn't match the MRZ. The consistency check must catch it.",
            {"status": ["FAIL", "REVIEW_REQUIRED"], "checks": {"consistency": ["FAIL", "REVIEW_REQUIRED"]}},
            ("image", "ocr", "negative"),
            lambda: ("passport-mismatch.png", _png(specimens.passport_image(printed_number="L898902C4")))),
    Builtin("doc-letter", "Ordinary letter", "documents", "A page with no identity data: nothing to check, and not a pass.",
            {"status": ["NOT_SUPPORTED", "FAIL", "REVIEW_REQUIRED"]},
            ("image", "ocr", "negative"), lambda: ("letter.png", _png(specimens.letter_image()))),
]

BY_KEY = {b.key: b for b in BUILTINS}
