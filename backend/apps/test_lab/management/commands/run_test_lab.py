"""Runs the Testing Laboratory from the command line, for example before a release or in CI.

    python manage.py run_test_lab
    python manage.py run_test_lab --module analyzer --junit results.xml

Exits with code 1 if any fixture fails or errors, so a script can stop on a regression.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings

from apps.test_lab.models import CaseResult
from apps.test_lab.services import RunInProgress, export_junit, start_run


class Command(BaseCommand):
    help = "Run the active fixtures and report the results."

    def add_arguments(self, parser):
        parser.add_argument("--module", choices=["analyzer", "documents"])
        parser.add_argument("--tag")
        parser.add_argument("--junit", help="Also write JUnit XML to this file.")
        parser.add_argument("--note", default="Command line")

    def handle(self, *args, **opts):
        scope = {k: opts[k] for k in ("module", "tag") if opts.get(k)}
        try:
            with override_settings(TEST_LAB_RUN_IN_BACKGROUND=False):
                run = start_run(None, scope, opts["note"])
        except (RunInProgress, ValueError) as problem:
            raise CommandError(str(problem))
        for case in run.cases.all():
            mark = {"PASS": self.style.SUCCESS("PASS "), "FAIL": self.style.ERROR("FAIL "), "ERROR": self.style.ERROR("ERROR")}[case.outcome]
            change = "  (new failure)" if case.change == CaseResult.NEW_FAILURE else "  (fixed)" if case.change == CaseResult.FIXED else ""
            self.stdout.write(f"{mark} {case.fixture_name}{change}")
            for row in case.comparisons:
                if not row["passed"]:
                    self.stdout.write(f"        {row['label']}: expected {row['expected']}, got {row['actual']}")
            if case.error:
                self.stdout.write(f"        {case.error}")
        if opts.get("junit"):
            Path(opts["junit"]).write_bytes(export_junit(run))
        summary = f"{run.reference}: {run.passed} passed, {run.failed} failed, {run.errors} errors, of {run.total}."
        if run.failed or run.errors:
            self.stdout.write(self.style.ERROR(summary))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(summary))
