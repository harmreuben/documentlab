"""Testing Laboratory: expectations, the synthetic-data guard, runs, regressions and exports."""
import csv
import io
import json
from datetime import timedelta
from xml.etree import ElementTree as ET

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.test_lab.models import CaseResult, Fixture, TestRun
from apps.test_lab.services import load_builtins
from core.ocr import engine as ocr
from core.testlab import builtin, expect, runner

from .images import AAMVA_LIKE, as_png, barcode, on_canvas, pdf417_raw
from .specimens import TD3_VALID

needs_ocr = pytest.mark.skipif(not ocr.status()[0], reason="Tesseract is not installed")
FIXTURES, RUNS = "/api/test-lab/fixtures/", "/api/test-lab/runs/"
EAN = "5901234123457"


@pytest.fixture(autouse=True)
def _runs_in_foreground(settings):
    settings.TEST_LAB_RUN_IN_BACKGROUND = False


def _png_file(name="ean.png", image=None):
    data = as_png(image or on_canvas(barcode("ean13", EAN[:12])))
    upload = io.BytesIO(data)
    upload.name = name
    return upload


def _add_fixture(client, **extra):
    body = {"name": "Shelf label", "module": "analyzer", "expected": json.dumps({"status": "PASS"}),
            "synthetic": "true", "file": _png_file(), **extra}
    return client.post(FIXTURES, body, format="multipart")


# --- Expectations ------------------------------------------------------------------------------

def test_expectation_validation_gives_plain_messages():
    assert expect.validate("analyzer", {"status": "PASS"}) == {"status": ["PASS"]}
    with pytest.raises(expect.InvalidExpectation, match="Not used for the Barcode Analyzer: fields"):
        expect.validate("analyzer", {"fields": {"surname": "X"}})
    with pytest.raises(expect.InvalidExpectation, match="status"):
        expect.validate("documents", {"status": "OK"})
    with pytest.raises(expect.InvalidExpectation, match="at least one"):
        expect.validate("documents", {})


def test_evaluate_reports_every_expectation_and_each_difference():
    actual = {"status": "FAIL", "summary": "", "duration_ms": 40, "barcode_count": 1,
              "barcodes": [{"format": "EAN-13", "text": EAN, "status": "FAIL"}], "checks": {"expected_value": "FAIL"}}
    rows = expect.evaluate("analyzer", expect.validate("analyzer", {
        "status": ["PASS"], "barcode_count": 1, "barcodes": [{"format": "EAN-13", "text": EAN}], "max_duration_ms": 10}), actual)
    assert [(r.label, r.passed) for r in rows] == [
        ("Overall result", False), ("Barcodes found", True), (f'Barcode: EAN-13 reading "{EAN}"', True), ("Time taken", False)]


def test_an_adopted_result_matches_itself():
    report = runner.analyse(runner.FixtureInput("documents", mrz_text="\n".join(TD3_VALID)))
    actual = expect.summarise("documents", report)
    expected = expect.validate("documents", expect.from_actual("documents", actual))
    assert all(r.passed for r in expect.evaluate("documents", expected, actual))


# --- Synthetic-data guard ----------------------------------------------------------------------

def test_guard_refuses_identity_barcodes_and_real_states():
    licence = runner.analyse(runner.FixtureInput("analyzer", "id.png", as_png(on_canvas(pdf417_raw(AAMVA_LIKE)))))
    assert "identity-document data" in runner.not_synthetic("analyzer", licence)
    real = "\n".join(line.replace("UTO", "KEN") for line in TD3_VALID)
    assert "KEN" in runner.not_synthetic("documents", runner.analyse(runner.FixtureInput("documents", mrz_text=real)))
    specimen = runner.analyse(runner.FixtureInput("documents", mrz_text="\n".join(TD3_VALID)))
    assert runner.not_synthetic("documents", specimen) is None


def test_no_standard_fixture_draws_a_licence_barcode():
    for spec in builtin.BUILTINS:
        if spec.make:
            name, data = spec.make()
            assert runner.not_synthetic(spec.module, runner.analyse(runner.FixtureInput(spec.module, name, data))) is None, spec.key


# --- The standard set is itself the regression suite --------------------------------------------

@needs_ocr
@pytest.mark.django_db
def test_every_standard_fixture_passes_on_this_build():
    load_builtins()
    call_command("run_test_lab", "--note", "pytest")
    run = TestRun.objects.get()
    failing = {c.fixture_name: [r for r in c.comparisons if not r["passed"]] or c.error
               for c in run.cases.exclude(outcome=CaseResult.PASS)}
    assert failing == {}
    assert run.status == TestRun.COMPLETE and run.passed == len(builtin.BUILTINS)


# --- API: permissions -------------------------------------------------------------------------

def test_who_can_do_what(client_as):
    reader, analyst, developer = client_as(Role.READ_ONLY), client_as(Role.ANALYST), client_as(Role.DEVELOPER)
    assert reader.get(FIXTURES).status_code == 200
    assert reader.get("/api/test-lab/meta/").json()["can_run"] is False
    assert analyst.post(FIXTURES + "load-builtin/").status_code == 403
    assert reader.post(RUNS, {}, format="json").status_code == 403
    assert developer.post(FIXTURES + "load-builtin/").json()["created"] == len(builtin.BUILTINS)
    assert analyst.post(RUNS, {"module": "documents", "tag": "typed"}, format="json").status_code == 201


def test_only_administrators_add_document_images(client_as):
    from .specimens import passport_image
    image = _png_file("passport.png", passport_image())
    response = _add_fixture(client_as(Role.DEVELOPER), module="documents", file=image)
    assert response.status_code == 403


# --- API: fixtures ---------------------------------------------------------------------------

def test_custom_fixture_needs_synthetic_confirmation_and_valid_expectation(client_as):
    developer = client_as(Role.DEVELOPER)
    assert "synthetic" in _add_fixture(developer, synthetic="false").json()["detail"]
    bad = _add_fixture(developer, expected=json.dumps({"status": "GREAT"}))
    assert bad.status_code == 400 and "status" in json.dumps(bad.json())
    broken = _add_fixture(developer, expected="{status: PASS")
    assert "isn't valid JSON" in json.dumps(broken.json())
    created = _add_fixture(developer)
    assert created.status_code == 201
    body = created.json()
    assert body["expected"] == {"status": ["PASS"]} and body["links"]["file"]
    assert developer.get(body["links"]["file"])["Content-Type"] == "image/png"


def test_identity_barcode_and_real_mrz_are_refused(client_as):
    admin = client_as(Role.ADMINISTRATOR)
    licence = _add_fixture(admin, file=_png_file("id.png", on_canvas(pdf417_raw(AAMVA_LIKE))))
    assert licence.status_code == 400 and "synthetic" in licence.json()["detail"]
    real = "\n".join(line.replace("UTO", "KEN") for line in TD3_VALID)
    refused = admin.post(FIXTURES, {"name": "x", "module": "documents", "expected": {"status": "PASS"},
                                    "synthetic": True, "mrz_text": real}, format="json")
    assert refused.status_code == 400 and "UTO" in refused.json()["detail"]
    assert not Fixture.objects.exists()
    logged = json.dumps([e.metadata for e in AuditEvent.objects.filter(action="testlab.fixture_refused")])
    assert logged.count("analyzer") == 1 and logged.count("documents") == 1
    for personal in ("ERIKSSON", "ANNA", "L898902C3", "SAMPLE", "T64235789", "1974"):
        assert personal not in logged


def test_standard_fixtures_are_fixed_in_code(client_as):
    developer = client_as(Role.DEVELOPER)
    developer.post(FIXTURES + "load-builtin/")
    fixture = Fixture.objects.get(builtin_key="doc-td3-valid")
    url = f"{FIXTURES}{fixture.pk}/"
    assert developer.patch(url, {"expected": {"status": "FAIL"}}, format="json").status_code == 400
    assert developer.delete(url).status_code == 400
    assert developer.patch(url, {"active": False}, format="json").json()["active"] is False
    # Loading again refreshes but doesn't duplicate.
    assert developer.post(FIXTURES + "load-builtin/").json() == {"created": 0, "updated": len(builtin.BUILTINS)}


def test_editing_a_custom_fixture(client_as):
    developer = client_as(Role.DEVELOPER)
    fixture = _add_fixture(developer).json()
    response = developer.patch(f"{FIXTURES}{fixture['id']}/", {"tags": "Shelf, Clean", "expected": {"barcode_count": 1}},
                               format="json")
    assert response.status_code == 200
    assert response.json()["tags"] == ["clean", "shelf"] and response.json()["expected"] == {"barcode_count": 1}
    assert developer.delete(f"{FIXTURES}{fixture['id']}/").status_code == 204


# --- API: runs, regressions, adoption, exports -------------------------------------------------

def test_runs_compare_with_the_previous_run(client_as):
    developer = client_as(Role.DEVELOPER)
    fixture = _add_fixture(developer, expected=json.dumps({"status": "PASS", "barcodes": [{"format": "EAN-13", "text": EAN}]})).json()
    first = developer.post(RUNS, {"note": "first"}, format="json").json()
    assert (first["status"], first["passed"], first["baseline"]) == ("COMPLETE", 1, None)
    assert first["cases"][0]["change"] == "new"

    # Someone changes the expectation wrongly: the next run must flag a new failure.
    developer.patch(f"{FIXTURES}{fixture['id']}/", {"expected": {"barcode_count": 2}}, format="json")
    second = developer.get(f"{RUNS}{developer.post(RUNS, {}, format='json').json()['id']}/").json()
    case = second["cases"][0]
    assert (second["failed"], second["new_failures"], case["change"], case["previous_outcome"]) == (1, 1, "new_failure", "PASS")
    assert case["comparisons"][0] == {"label": "Barcodes found", "expected": "2", "actual": "1", "passed": False}

    # Adopting the reviewed result as the expectation fixes it.
    adopted = developer.post(f"{FIXTURES}{fixture['id']}/adopt/", {"case_id": case["id"]}, format="json").json()
    assert adopted["expected"]["barcode_count"] == 1
    third = developer.post(RUNS, {}, format="json").json()
    assert third["cases"][0]["change"] == "fixed" and third["fixed"] == 1
    listed = [r["reference"] for r in developer.get(RUNS).json()["results"]]
    assert listed == [third["reference"], second["reference"], first["reference"]]  # newest first


def test_run_scope_and_empty_scope(client_as):
    developer = client_as(Role.DEVELOPER)
    assert "No active fixtures" in developer.post(RUNS, {}, format="json").json()["detail"]
    developer.post(FIXTURES + "load-builtin/")
    run = developer.post(RUNS, {"module": "documents", "tag": "typed"}, format="json").json()
    assert run["total"] == sum(1 for b in builtin.BUILTINS if b.module == "documents" and "typed" in b.tags)
    assert run["versions"]["app"] == "0.8.0"


def test_one_run_at_a_time_and_stale_runs_are_closed(client_as):
    developer = client_as(Role.DEVELOPER)
    _add_fixture(developer)
    stuck = TestRun.objects.create(status=TestRun.RUNNING, total=1)
    assert developer.post(RUNS, {}, format="json").status_code == 409
    TestRun.objects.filter(pk=stuck.pk).update(updated_at=timezone.now() - timedelta(minutes=11))
    assert developer.post(RUNS, {}, format="json").status_code == 201
    assert TestRun.objects.get(pk=stuck.pk).status == TestRun.INTERRUPTED


def test_a_missing_file_is_an_error_not_a_crash(client_as):
    developer = client_as(Role.DEVELOPER)
    fixture = Fixture.objects.get(pk=_add_fixture(developer).json()["id"])
    fixture.file.delete(save=False)
    run = developer.post(RUNS, {}, format="json").json()
    assert run["status"] == "COMPLETE" and run["errors"] == 1
    assert "couldn't be loaded" in run["cases"][0]["error"] or "error" in run["cases"][0]["error"]


def test_exports(client_as):
    developer = client_as(Role.DEVELOPER)
    _add_fixture(developer)
    _add_fixture(developer, name="Wrong count", expected=json.dumps({"barcode_count": 3}))
    run = developer.post(RUNS, {}, format="json").json()
    data = json.loads(developer.get(run["links"]["json"]).content)
    assert data["run"]["totals"] == {"total": 2, "passed": 1, "failed": 1, "errors": 0}
    rows = list(csv.DictReader(io.StringIO(developer.get(run["links"]["csv"]).content.decode("utf-8-sig"))))
    assert {r["fixture"]: r["outcome"] for r in rows} == {"Shelf label": "PASS", "Wrong count": "FAIL"}
    assert "expected 3, got 1" in next(r for r in rows if r["outcome"] == "FAIL")["differences"]
    suite = ET.fromstring(developer.get(run["links"]["junit"]).content)
    assert (suite.get("tests"), suite.get("failures")) == ("2", "1")
    assert suite.find("testcase/failure").get("message") == "Barcodes found: expected 3, got 1"
    assert developer.get(run["links"]["json"].replace("json", "pdf")).status_code == 400


def test_command_exits_with_an_error_when_something_fails(client_as):
    developer = client_as(Role.DEVELOPER)
    _add_fixture(developer, expected=json.dumps({"barcode_count": 5}))
    with pytest.raises(SystemExit) as stopped:
        call_command("run_test_lab")
    assert stopped.value.code == 1
