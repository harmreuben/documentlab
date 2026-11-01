"""core/identity: MRZ (ICAO 9303 specimens), SSN format rules, licence fields, comparison, full analysis."""
import pytest

from core.files import check_upload, load_pages
from core.identity import compare, licence, mrz, ssn
from core.identity.analyse import analyse_document, analyse_mrz_text
from core.ocr import engine as ocr

from . import images as img
from . import specimens as sp

needs_ocr = pytest.mark.skipif(not ocr.status()[0], reason="Tesseract is not installed")


def status_of(result, code):
    return next(c.status for c in result.checks if c.code == code)


# --- MRZ ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("data,digit", [("L898902C3", "6"), ("740812", "2"), ("120415", "9"), ("D23145890", "7"), ("<<<<<", "0")])
def test_icao_check_digits(data, digit):
    assert mrz.check_digit(data) == digit


@pytest.mark.parametrize("lines,layout,number", [(sp.TD3, "TD3", "L898902C3"), (sp.TD2, "TD2", "D23145890"), (sp.TD1, "TD1", "D23145890")])
def test_icao_specimens_parse_with_every_check_digit_passing(lines, layout, number):
    r = mrz.parse(lines, sp.TODAY)
    assert r.layout == layout
    assert r.fields["surname"]["value"] == "ERIKSSON" and r.fields["given_names"]["value"] == "ANNA MARIA"
    assert r.fields["document_number"]["value"] == number
    assert r.fields["birth_date"]["value"] == "1974-08-12"
    assert all(c.status == "PASS" for c in r.checks if c.code.startswith("mrz.check_digit"))
    assert status_of(r, "mrz.not_expired") == "FAIL"  # the specimens expired in 2012


def test_valid_specimen_passes_everything():
    r = mrz.parse(sp.TD3_VALID, sp.TODAY)
    assert r.status == "PASS" and r.fields["expiry_date"]["value"] == "2031-04-15"


def test_changed_birth_date_is_caught_by_two_check_digits():
    tampered = [sp.TD3_VALID[0], sp.TD3_VALID[1][:13] + "740813" + sp.TD3_VALID[1][19:]]
    r = mrz.parse(tampered, sp.TODAY)
    assert status_of(r, "mrz.check_digit.birth_date") == "FAIL"
    assert status_of(r, "mrz.check_digit.composite") == "FAIL"


def test_ocr_damage_is_repaired_and_listed():
    damaged = ["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<", sp.TD3_VALID[1].replace("UTO", "UT0")]
    r = mrz.parse(damaged, sp.TODAY)
    assert r.lines[0] == sp.TD3_VALID[0] and "UTO" in r.lines[1]
    assert {(c.line, c.found, c.used) for c in r.corrections} >= {(1, "", "<" * 8), (2, "0", "O")}
    assert status_of(r, "mrz.corrections") == "REVIEW_REQUIRED"  # country codes have no check digit


def test_misread_document_number_is_fixed_only_with_review():
    misread = [sp.TD3_VALID[0], "L8989O2C3" + sp.TD3_VALID[1][9:]]
    r = mrz.parse(misread, sp.TODAY)
    assert r.fields["document_number"]["value"] == "L898902C3"
    assert status_of(r, "mrz.check_digit.document_number") == "REVIEW_REQUIRED"
    assert status_of(r, "mrz.check_digit.composite") == "PASS"


def test_digit_corrections_confirmed_by_check_digits_need_no_review():
    r = mrz.parse([sp.TD3_VALID[0], sp.TD3_VALID[1][:13] + "74O8l2".upper() + sp.TD3_VALID[1][19:]], sp.TODAY)
    assert status_of(r, "mrz.corrections") == "PASS"


def test_missing_characters_in_a_data_line_are_not_guessed():
    r = mrz.parse([sp.TD3_VALID[0], sp.TD3_VALID[1][:40]], sp.TODAY)
    assert status_of(r, "mrz.line_length") == "FAIL" and r.fields == {}


def test_not_an_mrz():
    assert mrz.parse(["hello world"], sp.TODAY) is None


# --- SSN format --------------------------------------------------------------------------------

@pytest.mark.parametrize("number,valid,failing", [
    ("123-45-6780", True, None), ("123456780", True, None), ("123 45 6780", True, None),
    ("000-12-3456", False, "ssn.area"), ("666-12-3456", False, "ssn.area"), ("912-34-5678", False, "ssn.area"),
    ("123-00-4567", False, "ssn.group"), ("123-45-0000", False, "ssn.serial"),
    ("078-05-1120", False, "ssn.published"), ("12-345-6789", False, "ssn.shape"), ("123-45 6789", False, "ssn.shape"),
])
def test_ssn_format_rules(number, valid, failing):
    r = ssn.check(number)
    assert r.format_valid is valid
    if failing:
        assert status_of(r, failing) == "FAIL"
    assert status_of(r, "ssn.external") == "UNAVAILABLE"


def test_ssn_results_hold_only_the_masked_number():
    r = ssn.check("123-45-6780")
    assert r.masked == "***-**-6780"
    assert "12345" not in str(r.as_dict()) and "123-45" not in str(r.as_dict())


def test_ssn_valid_format_says_it_is_not_verification():
    assert "does not show that this number was issued" in ssn.check("123-45-6780").as_dict()["statement"]


# --- Licence fields ----------------------------------------------------------------------------

def test_licence_fields_are_read_for_comparison():
    r = licence.read(sp.LICENCE_PAYLOAD, sp.TODAY)
    values = {k: v["value"] for k, v in r.fields.items()}
    assert values["surname"] == "ERIKSSON" and values["given_names"] == "ANNA MARIA"
    assert values["birth_date"] == "1974-08-12" and values["document_number"] == "T64235789"
    assert status_of(r, "licence.jurisdiction_rules") == "UNAVAILABLE"


# --- Comparison --------------------------------------------------------------------------------

def doc(ref, kind, **fields):
    return {"reference": ref, "document_type": kind, "fields": {k: {"value": v} for k, v in fields.items()}}


def test_matching_documents():
    r = compare.compare([doc("A", "passport", surname="Eriksson", birth_date="1974-08-12"),
                         doc("B", "driving_licence", surname="ERIKSSON", birth_date="1974-08-12")])
    assert r["status"] == "PASS"


def test_near_names_need_review_and_different_dates_fail():
    r = compare.compare([doc("A", "passport", given_names="ANNA MARIA", birth_date="1974-08-12"),
                         doc("B", "driving_licence", given_names="Anna Marïa", birth_date="1974-08-13")])
    rows = {row["field"]: row for row in r["rows"]}
    assert rows["given_names"]["status"] == "PASS"  # accents and case are ignored
    assert rows["birth_date"]["status"] == "FAIL" and r["status"] == "FAIL"
    r = compare.compare([doc("A", "passport", surname="ERIKSSON"), doc("B", "id_card", surname="ERIKSON")])
    assert r["rows"][0]["status"] == "REVIEW_REQUIRED"


def test_document_numbers_only_compared_within_one_document_type():
    r = compare.compare([doc("A", "passport", document_number="L898902C3"),
                         doc("B", "driving_licence", document_number="T64235789")])
    row = next(x for x in r["rows"] if x["field"] == "document_number")
    assert row["status"] == "NOT_CHECKED"


# --- Whole documents ---------------------------------------------------------------------------

def analyse_image(image, kind="auto"):
    data = img.as_png(image)
    k, w = check_upload("scan.png", data)
    return analyse_document(load_pages(k, data), kind, w, sp.TODAY)


def test_typed_mrz_never_claims_authenticity():
    r = analyse_mrz_text("\n".join(sp.TD3_VALID), "passport", sp.TODAY)
    assert r.status == "PASS" and r.as_dict()["authenticity"]["status"] == "NOT_CHECKED"
    assert status_of(r, "external.verification") == "UNAVAILABLE"


@needs_ocr
def test_passport_image_mrz_is_read_by_ocr():
    r = analyse_image(sp.passport_image())
    assert r.detected_type == "passport"
    assert r.fields["document_number"]["value"] == "L898902C3"
    assert all(c.status == "PASS" for c in r.checks if c.code.startswith("mrz.check_digit"))


@needs_ocr
def test_printed_name_that_differs_from_the_mrz_is_flagged():
    r = analyse_image(sp.passport_image(printed_given="ANNA MARTHA"))
    assert status_of(r, "consistency.given_names") == "REVIEW_REQUIRED"


@needs_ocr
def test_document_without_machine_readable_data_is_text_only():
    r = analyse_image(sp.letter_image())
    assert r.status == "NOT_SUPPORTED" and r.detected_type == "other"


def test_licence_barcode_is_read_without_ocr_text():
    r = analyse_image(img.pdf417_raw(sp.LICENCE_PAYLOAD), "driving_licence")
    assert r.detected_type == "driving_licence" and r.fields["surname"]["value"] == "ERIKSSON"
    assert r.status in ("PASS", "UNAVAILABLE")


def test_requested_type_mismatch_is_flagged():
    r = analyse_image(img.pdf417_raw(sp.LICENCE_PAYLOAD), "passport")
    assert status_of(r, "document.type") == "REVIEW_REQUIRED"
