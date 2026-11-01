"""The rule catalogue must describe every check the code actually makes, and coverage must be measured."""
import re
from pathlib import Path

import pytest

from apps.accounts.models import Role
from apps.test_lab.services import load_builtins, start_run
from core.barcodes.analyse import analyse as analyse_barcodes
from core.files import load_pages
from core.identity import compare, ssn
from core.identity.analyse import analyse_document, analyse_mrz_text
from core.imaging import quality
from core.rules.catalogue import BY_CODE, RULES, RULESET_VERSION, rule_for

from .images import as_png, barcode, on_canvas, pdf417_raw
from .specimens import LICENCE_PAYLOAD, TD1, TD2, TD3, TD3_VALID, TODAY

IDENTITY_SOURCE = Path(__file__).resolve().parent.parent / "core" / "identity"


def test_rule_codes_are_unique_and_complete():
    assert len(BY_CODE) == len(RULES)
    for rule in RULES:
        assert rule.name and rule.checks and rule.outcomes, rule.code
        assert set(rule.outcomes) <= {"PASS", "FAIL", "REVIEW_REQUIRED", "NOT_SUPPORTED", "UNAVAILABLE", "NOT_CHECKED"}
        assert all(len(change) == 3 for change in rule.changes)
        assert rule.version == 1 + len(rule.changes) or rule.version > 1, rule.code


def test_every_check_code_written_in_the_identity_code_is_catalogued():
    """Static scan: a new Check(...) in core/identity without a rule fails here."""
    pattern = re.compile(r'Check\(\s*"[a-z_]+",\s*f?"([a-z_.{}]+)"')
    codes = {m for f in IDENTITY_SOURCE.glob("*.py") for m in pattern.findall(f.read_text(encoding="utf-8"))}
    assert len(codes) > 30
    for code in codes:
        if "{" in code:  # f-string: check a concrete example of it
            code = code.replace("{key}", "birth_date").replace("{name}", "composite")
        assert rule_for(code) is not None, f"No rule in core/rules/catalogue.py produces {code!r}"


def _codes(report) -> set[str]:
    return {c["code"] for c in report.as_dict()["checks"]}


def test_every_check_produced_at_run_time_is_catalogued():
    reports = [analyse_mrz_text("\n".join(lines), kind, TODAY) for lines, kind in
               [(TD3_VALID, "auto"), (TD3, "auto"), (TD2, "auto"), (TD1, "auto"), (TD3_VALID, "id_card"), (["HELLO"], "auto")]]
    licence = load_pages("png", as_png(on_canvas(pdf417_raw(LICENCE_PAYLOAD))))
    reports.append(analyse_document(licence, "auto", None, TODAY))
    for code in set().union(*map(_codes, reports)):
        assert rule_for(code, "documents"), code
    for number in ("212-34-5678", "666-12-3456", "078-05-1120", "123456789", "12-345"):
        for check in ssn.check(number).as_dict()["checks"]:
            assert rule_for(check["code"], "ssn"), check["code"]
    barcode_report = analyse_barcodes(load_pages("png", as_png(on_canvas(barcode()))), "5901234123457")
    for check in barcode_report.checks:
        assert rule_for(check.category, "analyzer"), check.category
    for key, *_ in compare.FIELDS:
        assert rule_for(f"compare.{key}", "comparison"), key


def test_published_thresholds_are_the_ones_in_use():
    params = BY_CODE["barcode.image_quality"].parameters
    assert params["Smallest long side"] == f"{quality.MIN_LONG_SIDE_PX} px"
    assert str(int(quality.BLUR_SHARPNESS_MIN)) in params["Lowest sharpness"]


def test_rules_api_reports_measured_coverage(client_as, settings):
    settings.TEST_LAB_RUN_IN_BACKGROUND = False
    reader = client_as(Role.READ_ONLY)
    before = reader.get("/api/rules/").json()
    assert before["ruleset_version"] == RULESET_VERSION
    assert before["coverage_summary"]["full"] == 0 and before["measured_from"]["latest_run"] is None

    load_builtins()
    start_run(None, {})
    rules = {r["code"]: r for r in reader.get("/api/rules/").json()["rules"]}
    digits = rules["mrz.check_digit.*"]["coverage"]
    assert digits["level"] == "full" and {"PASS", "FAIL"} <= set(digits["statuses"])
    assert any(f["name"] == "Passport MRZ, wrong check digit" for f in digits["asserted_by"])
    assert rules["ssn.area"]["coverage"]["level"] == "outside"
    assert rules["mrz.name_truncated"]["coverage"]["level"] == "none"  # honest: no fixture has a truncated name yet
    assert rules["barcode.image_quality"]["severity"] == "review"
    assert rules["barcode.image_quality"]["changes"][0]["app_version"] == "0.6.0"


@pytest.mark.django_db
def test_new_records_carry_the_rule_set_version(client_as):
    analyst = client_as(Role.ANALYST)
    doc = analyst.post("/api/documents/analyses/", {"mrz_text": "\n".join(TD3_VALID), "authorised": True},
                       format="json").json()
    assert doc["ruleset_version"] == RULESET_VERSION
    assert analyst.post("/api/documents/ssn-checks/", {"number": "212-34-5678"}, format="json").json()["ruleset_version"] == RULESET_VERSION
