"""core/barcodes/analyse, core/files, core/imaging - no database."""
import numpy as np
import pytest
import zxingcpp
from PIL import Image

from core.barcodes.analyse import analyse
from core.barcodes.interpret import interpret
from core.files import FileRejected, check_upload, load_pages
from core.imaging.quality import assess_image

from . import images as img


def run(image_or_bytes, expected=None, name="scan.png"):
    data = image_or_bytes if isinstance(image_or_bytes, bytes) else img.as_png(image_or_bytes)
    kind, warnings = check_upload(name, data)
    return analyse(load_pages(kind, data), expected, warnings)


def check(report, category):
    return next(c for c in report.checks if c.category == category).status


# --- Files ---------------------------------------------------------------------------------

@pytest.mark.parametrize("data,name,message", [
    (b"", "a.png", "empty"),
    (b"GIF89a" + b"0" * 20, "a.gif", "Only PNG, JPEG and PDF"),
    (b"not an image at all", "a.png", "Only PNG, JPEG and PDF"),
    (b"\x89PNG\r\n\x1a\n" + b"0" * 50, "a.png", None),  # right signature, broken body -> refused on load
])
def test_unusable_files_are_refused(data, name, message):
    with pytest.raises(FileRejected) as err:
        kind, _ = check_upload(name, data)
        load_pages(kind, data)
    if message:
        assert message in str(err.value)


def test_files_over_10mb_are_refused():
    with pytest.raises(FileRejected, match="limit is 10 MB"):
        check_upload("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024))


def test_type_comes_from_content_not_name():
    kind, warnings = check_upload("photo.jpg", img.as_png(img.barcode()))
    assert kind == "png" and "really a PNG" in warnings[0]


def test_jpeg_and_pdf_are_accepted():
    assert run(img.as_jpeg(img.barcode()), name="a.jpg").status == "PASS"
    report = run(img.pdf_with([img.barcode()], blank_first=True), name="scan.pdf")
    assert report.status == "PASS" and report.barcodes[0].page == 2


# --- Quality indicators ------------------------------------------------------------------

def test_clean_generated_image_has_no_quality_findings():
    assert assess_image(img.barcode()).findings == []


def test_a_blank_page_is_called_blank_not_blurred():
    from PIL import Image
    findings = assess_image(Image.new("RGB", (900, 600), "white")).findings
    assert [f.code for f in findings] == ["blank"]
    assert "blank" in findings[0].message


def test_blur_and_low_contrast_are_reported():
    assert "blurred" in {f.code for f in assess_image(img.blurred(img.barcode())).findings}
    assert "low_contrast" in {f.code for f in assess_image(img.low_contrast(img.barcode())).findings}


# --- Results ---------------------------------------------------------------------------------

def test_clean_barcode_passes_every_check():
    report = run(img.barcode())
    assert report.status == "PASS"
    assert {c.category: c.status for c in report.checks} == {
        "file_integrity": "PASS", "image_quality": "PASS", "barcode_decoding": "PASS",
        "data_format": "PASS", "expected_value": "NOT_CHECKED"}
    b = report.barcodes[0]
    assert b.text == "5901234123457" and b.consistent_reads == b.attempts == 3


def test_unreadable_image_fails_and_explains_why():
    report = run(img.blurred(img.barcode()))
    assert report.status == "FAIL" and report.summary == "No barcode could be read."
    assert "blurred" in report.next_action


def test_expected_value_match_and_mismatch():
    assert check(run(img.barcode(), "5901234123457"), "expected_value") == "PASS"
    report = run(img.barcode(), "5901234123458")
    assert report.status == "FAIL" and check(report, "expected_value") == "FAIL"


def test_low_contrast_that_still_reads_passes_with_advice():
    report = run(img.low_contrast(img.barcode()))
    assert report.status == "PASS" and check(report, "image_quality") == "REVIEW_REQUIRED"
    assert report.next_action.startswith("The barcode read correctly, but")


def test_multiple_barcodes_are_all_found():
    report = run(img.on_canvas(img.barcode("qr", "https://example.test/x"), img.barcode()))
    assert {b.format_name for b in report.barcodes} == {"QR Code", "EAN-13"}
    assert check(report, "data_format") == "PASS"


def test_unsupported_format_is_read_but_not_passed():
    dm = zxingcpp.create_barcode("TEST-DM-1", zxingcpp.BarcodeFormat.DataMatrix).to_image(scale=10)
    report = run(img.on_canvas(Image.fromarray(np.array(dm)).convert("RGB"), size=(500, 400)))
    assert report.status == "NOT_SUPPORTED" and report.barcodes[0].text == "TEST-DM-1"


def test_identity_payload_is_never_compared_with_an_expected_value():
    # Answering "matches" or "doesn't match" would let someone guess withheld data.
    for guess in ("DAQT64235789", "wrong"):
        report = run(img.pdf417_raw(img.AAMVA_LIKE), guess)
        assert report.barcodes[0].expected_match is None
        assert check(report, "expected_value") == "NOT_CHECKED"
        assert report.status == "REVIEW_REQUIRED"


def test_long_thin_stacked_code_is_not_called_low_resolution():
    assert assess_image(img.pdf417_raw("TEST-STACKED-0001")).findings == []


def test_identity_payload_is_withheld_and_never_passes():
    report = run(img.pdf417_raw(img.AAMVA_LIKE))
    assert report.status == "REVIEW_REQUIRED" and report.sensitive
    b = report.barcodes[0]
    assert b.text is None and b.alternatives == {}
    assert "Document Analysis" in report.next_action


def test_structured_documentlab_payload_is_validated():
    report = run(img.barcode("qr", None, "documentlab.asset-tag.v1", {"asset_id": "TEST-1", "name": "Scanner"}))
    meaning = report.barcodes[0].interpretation
    assert meaning["kind"] == "documentlab_schema" and meaning["data_check"] == "PASS"


def test_code39_plus_percent_matches_expected_via_standard_reading():
    report = run(img.barcode("code39", "A+B%C"), "A+B%C")
    assert report.status == "PASS" and report.barcodes[0].alternatives["code39_standard"] == "A+B%C"


# --- Interpretation ------------------------------------------------------------------------

def test_wrong_retail_check_digit_is_a_data_failure():
    meaning = interpret("ean13", "5901234123458", b"")
    assert meaning.data_check == "FAIL" and "should be 7" in meaning.data_detail


def test_schema_with_bad_field_fails():
    meaning = interpret("qr", '{"schema":"documentlab.shipment-label.v1","shipment_ref":"x y","origin":"A",'
                              '"destination":"B","pieces":0}', b"")
    assert meaning.data_check == "FAIL"


def test_urls_are_described_not_opened():
    meaning = interpret("qr", "http://example.test/a", b"")
    assert meaning.kind == "url" and any("not encrypted" in n for n in meaning.notes)


def test_upca_note_on_leading_zero_ean13():
    assert any("UPC-A" in n for n in interpret("ean13", "0036000291452", b"").notes)
