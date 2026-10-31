"""Tests for core/barcodes: no database, no Django - pure rules."""
import pytest

from core.barcodes import check, generate
from core.barcodes.guards import identity_layout_reason
from core.barcodes.options import contrast_ratio
from core.barcodes.samples import sample
from core.barcodes.schemas import SCHEMAS, TEXT_SCHEMA
from core.barcodes.symbologies import SYMBOLOGIES, gs1_check_digit
from core.barcodes.verify import FAIL, verify


def messages(result):
    return " | ".join(e["message"] for e in result.errors)


# --- Check digits (published GS1 examples) ------------------------------------------------

@pytest.mark.parametrize("data,digit", [
    ("590123412345", "7"),   # EAN-13 example
    ("400638133393", "1"),   # EAN-13
    ("9638507", "4"),        # EAN-8
    ("03600029145", "2"),    # UPC-A
])
def test_gs1_check_digits(data, digit):
    assert gs1_check_digit(data) == digit


def test_short_ean13_gets_its_check_digit_added():
    r = check("ean13", "590123412345")
    assert r.ok and r.expected_decode == "5901234123457" and r.check_digit == "7"


def test_wrong_check_digit_is_refused_with_the_right_one():
    r = check("ean13", "5901234123458")
    assert not r.ok
    assert "should be 7, not 8" in messages(r)


@pytest.mark.parametrize("fmt,data,expected", [
    ("ean13", "12345", "needs 12 digits"),
    ("ean8", "12A4567", "digits only"),
    ("upca", "1234567890123", "needs 11 digits"),
    ("code128", "café", "plain keyboard characters"),
    ("code39", "TEST#1", "Remove: #"),
    ("code128", "X" * 81, "at most 80 characters"),
    ("qr", "   ", "Enter the data"),
])
def test_invalid_payloads_explain_what_is_wrong(fmt, data, expected):
    r = check(fmt, data)
    assert not r.ok
    assert expected in messages(r)


def test_code39_lowercase_is_capitalised_with_a_warning():
    r = check("code39", "asset-9")
    assert r.ok and r.expected_decode == "ASSET-9"
    assert "capitals" in r.warnings[0]["message"]


def test_unknown_format_is_refused():
    assert "supported barcode format" in messages(check("aztec", "x"))


# --- Identity-layout guard ------------------------------------------------------------------

AAMVA_LIKE = "@\n\x1e\rANSI 636000080002DL00410278ZV03190008DLDAQT64235789\nDCSSAMPLE\nDBB01011990"
MRZ_LIKE = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"


@pytest.mark.parametrize("payload", [
    AAMVA_LIKE,
    "ANSI 636000080002",
    "DAQ12345678\nDCSTEST\nDACTEST\nDBB19900101",
    MRZ_LIKE,
    MRZ_LIKE.replace("\n", ""),
])
def test_identity_layouts_are_refused_in_every_format(payload):
    assert identity_layout_reason(payload)
    for fmt in ("qr", "pdf417", "code128"):
        r = check(fmt, payload)
        assert not r.ok and r.blocked


@pytest.mark.parametrize("payload", [
    "Meeting notes: DAQ team review on ANSI standards",
    "https://example.test/items/TEST-0042",
    "Order 2026-10-31 <<urgent>>",
    '{"schema":"documentlab.asset-tag.v1","asset_id":"TEST-AST-0042"}',
])
def test_ordinary_text_is_not_blocked(payload):
    assert identity_layout_reason(payload) is None


# --- Schemas --------------------------------------------------------------------------------

def test_structured_payload_is_compact_json_with_schema_first():
    r = check("qr", schema_id="documentlab.asset-tag.v1", fields={"asset_id": "TEST-1", "name": "Scanner"})
    assert r.ok
    assert r.expected_decode == '{"schema":"documentlab.asset-tag.v1","asset_id":"TEST-1","name":"Scanner"}'


def test_schema_field_rules():
    r = check("pdf417", schema_id="documentlab.shipment-label.v1",
              fields={"shipment_ref": "bad ref", "origin": "A", "destination": "B", "pieces": "0", "weight_kg": "abc"})
    fields = {e["field"] for e in r.errors}
    assert fields == {"shipment_ref", "pieces", "weight_kg"}


def test_unknown_schema_fields_are_refused():
    r = check("qr", schema_id="documentlab.asset-tag.v1",
              fields={"asset_id": "TEST-1", "name": "X", "date_of_birth": "1990-01-01"})
    assert not r.ok and "not part of" in messages(r)


def test_linear_formats_cannot_take_structured_schemas():
    r = check("ean13", schema_id="documentlab.asset-tag.v1", fields={"asset_id": "T-1", "name": "X"})
    assert "Use QR Code or PDF417" in messages(r)


# --- Options --------------------------------------------------------------------------------

def test_contrast_ratio_black_on_white_is_21():
    assert round(contrast_ratio("#000000", "#FFFFFF")) == 21


@pytest.mark.parametrize("options,expected", [
    ({"foreground": "#FFFFFF", "background": "#000000"}, "dark bars on a light background"),
    ({"foreground": "#CCCCCC", "background": "#FFFFFF"}, "too close"),
    ({"foreground": "red"}, "colour like"),
    ({"module_width": 5}, "between 0.19 and 1"),
    ({"dpi": 72.5}, "whole number"),
])
def test_bad_options_are_refused(options, expected):
    r = check("code128", "TEST-1", options)
    assert not r.ok and expected in messages(r)


def test_small_qr_quiet_zone_only_warns():
    r = check("qr", "TEST", {"border": 1})
    assert r.ok and any(w["field"] == "border" for w in r.warnings)


# --- Round trip: every format and schema, using the sample data -------------------------------

COMBINATIONS = [(f, s) for f in SYMBOLOGIES for s in SCHEMAS
                if s == TEXT_SCHEMA or SYMBOLOGIES[f].structured]


@pytest.mark.parametrize("fmt,schema_id", COMBINATIONS)
def test_every_sample_generates_and_decodes_exactly(fmt, schema_id):
    data = sample(fmt, schema_id, seed=7)
    result = generate(fmt, data.get("payload"), {}, schema_id, data.get("fields"))
    assert result.ok, result.check.errors
    assert result.verification.status == "PASS", result.verification.detail
    assert result.verification.decoded_text == result.check.expected_decode
    assert result.output.png.startswith(b"\x89PNG")
    assert "<svg" in result.output.svg


def test_coloured_codes_still_verify():
    r = generate("qr", "TEST-COLOUR", {"foreground": "#0E1726", "background": "#F3F5F8"})
    assert r.verification.status == "PASS"


def test_upca_is_matched_despite_the_decoders_leading_zero():
    r = generate("upca", "03600029145")
    assert r.verification.status == "PASS" and r.check.expected_decode == "036000291452"


def test_code39_with_plus_and_percent_is_read_as_standard_code39():
    r = generate("code39", "A+B%C")
    assert r.verification.status == "PASS" and r.verification.decoded_text == "A+B%C"


def test_short_pdf417_adjusts_its_columns_and_says_so():
    r = generate("pdf417", "abc", {"columns": 20})
    assert r.ok and r.verification.status == "PASS"
    assert any(w["field"] == "columns" for w in r.check.warnings)


def test_verification_fails_when_the_image_does_not_match():
    r = generate("code128", "TEST-A")
    v = verify(SYMBOLOGIES["code128"], r.output.png, "TEST-B")
    assert v.status == FAIL and v.decoded_text == "TEST-A"


def test_verification_fails_on_an_image_with_no_barcode():
    import io
    from PIL import Image
    blank = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(blank, "PNG")
    assert verify(SYMBOLOGIES["qr"], blank.getvalue(), "x").status == FAIL


def test_qr_overflow_is_reported_not_crashed():
    r = generate("qr", "€" * 1000, {"error_correction": "H"})  # 3000 bytes; level H holds 1273
    assert not r.ok and "too long for a QR code" in messages(r.check)
