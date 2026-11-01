"""The content of each report. Layout is in core.reports.pdf.

What each report may contain:
- Barcode analysis: everything on the result page. Withheld identity data stays withheld.
- Document analysis: the document's personal data, so it carries a confidentiality banner and its
  deletion date. After the data is deleted, only the outline remains.
- Test run and summary reports: no personal data at all. The summary has counts only.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Role
from apps.barcode_decoder.models import BarcodeAnalysis
from apps.document_analysis.models import DocumentAnalysis, SsnCheck
from apps.reviews.models import ReviewState
from apps.test_lab.models import TestRun
from core.reports.pdf import esc, facts, render, status, table
from core.rules.catalogue import RULESET_VERSION, rule_for

AUTHENTICITY_NOTE = ("These are technical checks. They don't show that a document is genuine, or that it belongs "
                     "to the person presenting it.")
IDENTITY_ROLES = (Role.ADMINISTRATOR, Role.ANALYST, Role.REVIEWER)
SEES_ALL = (Role.ADMINISTRATOR, Role.REVIEWER)


def _when(value) -> str:
    return timezone.localtime(value).strftime("%d %b %Y, %H:%M") if value else "—"


def _review_html(record) -> str:
    if not record.review_state:
        return ""
    label = ReviewState(record.review_state).label
    by = f" by {record.reviewed_by.get_username()}" if record.reviewed_by else ""
    when = f" on {_when(record.reviewed_at)}" if record.reviewed_at else ""
    note = f'<p class="small">Note: {esc(record.review_note)}</p>' if record.review_note else ""
    return f"<h2>Review</h2><p>{esc(label)}{esc(by)}{esc(when)}.</p>{note}"


# --- One barcode analysis -------------------------------------------------------------------------

def barcode_analysis_pdf(a: BarcodeAnalysis) -> bytes:
    body = facts([
        ("Result", {"PASS": "Pass", "FAIL": "Fail", "REVIEW_REQUIRED": "Needs review"}.get(a.status, a.status)),
        ("Summary", a.summary), ("Next step", a.next_action),
        ("File", f"{a.upload.original_name} ({a.upload.kind.upper()}, {a.upload.size_bytes:,} bytes)"),
        ("SHA-256", a.upload.sha256), ("Expected value", a.expected_value or "None given"),
        ("Analysed", f"{_when(a.created_at)} by {a.created_by.get_username() if a.created_by else 'unknown'}"),
        ("Decoder", a.decoder), ("Rule set", a.ruleset_version or "Before rule versioning"),
    ])
    body += "<h2>Checks</h2>" + table(["Check", "Result", "Detail"], [
        [esc(c["category"].replace("_", " ").capitalize()), status(c["status"]), esc(c["detail"])] for c in a.checks], raw=True)
    rows = []
    for b in a.barcodes.all():
        text = "Withheld (identity-document data)" if b.text is None else b.text
        rows.append([esc(f"Page {b.page}, #{b.index}"), esc(b.format_name), f'<span class="mono">{esc(text[:300])}</span>',
                     status(b.status), esc(f"{b.reason} Read {b.consistent_reads} of {b.attempts} times.")])
    body += "<h2>Barcodes</h2>" + (table(["Where", "Format", "Data", "Result", "Why"], rows, raw=True) if rows
                                    else "<p>No barcode was found.</p>")
    body += _review_html(a)
    return render(f"Barcode analysis {a.reference}", body, subtitle="Barcode Analyzer report")


# --- One document analysis ------------------------------------------------------------------------

def document_analysis_pdf(d: DocumentAnalysis) -> bytes:
    from core.identity.analyse import TYPES
    banner = ("" if d.purged_at else
              f"CONFIDENTIAL: contains personal data. Handle under your data-protection rules and delete when no "
              f"longer needed. DocumentLab deletes this record's data on {timezone.localtime(d.expires_at):%d %b %Y}.")
    body = facts([
        ("Document", TYPES.get(d.detected_type, "Unknown document") + (" (typed MRZ)" if d.source == "manual_mrz" else "")),
        ("Result", {"PASS": "Pass", "FAIL": "Fail", "REVIEW_REQUIRED": "Needs review"}.get(d.status, d.status)),
        ("Summary", d.summary), ("Next step", d.next_action),
        ("Analysed", f"{_when(d.created_at)} by {d.created_by.get_username() if d.created_by else 'unknown'}"),
        ("Rule set", d.ruleset_version or "Before rule versioning"),
    ])
    body += f'<div class="notice"><b>Authenticity not checked.</b> {esc(AUTHENTICITY_NOTE)}</div>'
    if d.purged_at:
        body += f"<p>Personal data was deleted on {_when(d.purged_at)} ({esc(d.purge_reason)}). Only check results remain.</p>"
    else:
        if d.mrz:
            lines = "<br/>".join(esc(line) for line in d.mrz["lines"])
            body += f'<h2>Machine-readable zone ({esc(d.mrz["layout"])})</h2><p class="mono">{lines}</p>'
        if d.fields:
            body += "<h2>Extracted fields</h2>" + table(["Field", "Value", "Source"], [
                [f["label"], f.get("display") or f.get("value", ""), f.get("source", "")]
                for k, f in d.fields.items() if k not in ("first_name", "middle_names")])
    body += "<h2>Checks</h2>" + table(["Check", "Result", "Detail"], [
        [esc(c.get("name") or c.get("code")), status(c["status"]), esc(c.get("detail", ""))] for c in d.checks], raw=True)
    body += _review_html(d)
    return render(f"Document analysis {d.reference}", body, subtitle="Document Analysis report", banner=banner,
                  footer_note="" if d.purged_at else "Confidential")


# --- One test run ---------------------------------------------------------------------------------

def test_run_pdf(run: TestRun) -> bytes:
    v = run.versions or {}
    body = facts([
        ("Outcome", f"{run.passed} of {run.total} passed, {run.failed} failed, {run.errors} errors"),
        ("Started", f"{_when(run.created_at)} by {run.created_by.get_username() if run.created_by else 'command line'}"),
        ("Note", run.note or "—"), ("Compared with", run.baseline.reference if run.baseline else "Nothing (first run)"),
        ("Build", f"DocumentLab {v.get('app', '?')} · rules {v.get('rules', '?')} · {v.get('decoder', '?')} · {v.get('ocr', '?')}"),
    ])
    changed = {"new_failure": "New failure", "fixed": "Fixed", "still_failing": "Still failing", "new": "New"}
    rows = []
    for c in run.cases.all():
        diffs = "; ".join(f"{r['label']}: expected {r['expected']}, got {r['actual']}" for r in c.comparisons if not r["passed"])
        rows.append([esc(c.fixture_name), esc(c.module), status(c.outcome), esc(changed.get(c.change, "")),
                     esc(diffs or c.error or "As expected")])
    body += "<h2>Results</h2>" + table(["Fixture", "Module", "Outcome", "Change", "Details"], rows, raw=True)
    return render(f"Test run {run.reference}", body, subtitle="Testing Laboratory report")


# --- Summary for a period ---------------------------------------------------------------------------

def period(start: date, end: date):
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(start, time.min), tz),
            timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz))


def summary(user, start: date, end: date) -> dict:
    """Counts only. Administrators and reviewers see everyone's work; other roles see their own."""
    since, until = period(start, end)
    everyone = user.role in SEES_ALL

    def scoped(qs, owner="created_by"):
        qs = qs.filter(created_at__gte=since, created_at__lt=until)
        return qs if everyone else qs.filter(**{owner: user})

    sections: dict = {}
    failing: Counter = Counter()
    reviewing: Counter = Counter()

    barcodes = scoped(BarcodeAnalysis.objects.all())
    sections["analyzer"] = _section("Barcode Analyzer", barcodes)
    for checks in barcodes.values_list("checks", flat=True):
        for c in checks:
            _tally(rule_for(c["category"], "analyzer"), c["status"], failing, reviewing)

    if user.role in IDENTITY_ROLES:
        documents = scoped(DocumentAnalysis.objects.all())
        sections["documents"] = _section("Document Analysis", documents)
        for checks in documents.values_list("checks", flat=True):
            for c in checks:
                _tally(rule_for(c.get("code", ""), "documents"), c["status"], failing, reviewing)
        ssn = scoped(SsnCheck.objects.all())
        sections["ssn"] = {"label": "SSN format checks", "total": ssn.count(),
                           "by_status": dict(Counter(ssn.values_list("status", flat=True)))}

    runs = scoped(TestRun.objects.filter(status=TestRun.COMPLETE))
    last = runs.order_by("-created_at").first()
    sections["test_lab"] = {
        "label": "Testing Laboratory", "runs": runs.count(),
        "runs_with_failures": runs.filter(failed__gt=0).count() + runs.filter(failed=0, errors__gt=0).count(),
        "last_run": {"reference": last.reference, "passed": last.passed, "total": last.total} if last else None,
    }
    from core.rules.catalogue import BY_CODE
    top = [{"code": code, "name": BY_CODE[code].name, "module": BY_CODE[code].module, "failed": failing[code],
            "review": reviewing[code]} for code in sorted(set(failing) | set(reviewing),
                                                           key=lambda k: (-failing[k], -reviewing[k], k))][:12]
    return {
        "start": start.isoformat(), "end": end.isoformat(), "scope": "everyone" if everyone else "own",
        "generated_by": user.get_username(), "generated_at": timezone.now().isoformat(),
        "app_version": settings.APP_VERSION, "ruleset_version": RULESET_VERSION,
        "sections": sections, "rules": top,
    }


def _section(label: str, qs) -> dict:
    return {"label": label, "total": qs.count(), "by_status": dict(Counter(qs.values_list("status", flat=True))),
            "reviews": dict(Counter(s for s in qs.values_list("review_state", flat=True) if s))}


def _tally(rule, result: str, failing: Counter, reviewing: Counter) -> None:
    if rule is None:
        return
    if result == "FAIL":
        failing[rule.code] += 1
    elif result == "REVIEW_REQUIRED":
        reviewing[rule.code] += 1


STATUS_ORDER = ["PASS", "REVIEW_REQUIRED", "FAIL", "NOT_SUPPORTED", "UNAVAILABLE", "NOT_CHECKED"]
REVIEW_ORDER = ["PENDING", "CONFIRMED", "REJECTED", "EXPIRED"]


def summary_csv(data: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["section", "measure", "value"])
    w.writerow(["report", "period", f"{data['start']} to {data['end']}"])
    w.writerow(["report", "scope", "all users" if data["scope"] == "everyone" else f"{data['generated_by']} only"])
    w.writerow(["report", "rule set", data["ruleset_version"]])
    for key, s in data["sections"].items():
        if "total" in s:
            w.writerow([s["label"], "total", s["total"]])
            for st in STATUS_ORDER:
                if s["by_status"].get(st):
                    w.writerow([s["label"], f"result: {st}", s["by_status"][st]])
            for rs in REVIEW_ORDER:
                if s.get("reviews", {}).get(rs):
                    w.writerow([s["label"], f"review: {rs}", s["reviews"][rs]])
        else:
            w.writerow([s["label"], "completed runs", s["runs"]])
            w.writerow([s["label"], "runs with failures or errors", s["runs_with_failures"]])
    for r in data["rules"]:
        w.writerow(["rules", f"{r['code']} failed", r["failed"]])
        w.writerow(["rules", f"{r['code']} needed review", r["review"]])
    return ("﻿" + out.getvalue()).encode()


def summary_pdf(data: dict) -> bytes:
    words = {"PASS": "Pass", "FAIL": "Fail", "REVIEW_REQUIRED": "Needs review", "NOT_SUPPORTED": "Not supported",
             "UNAVAILABLE": "Unavailable", "NOT_CHECKED": "Not checked", "PENDING": "Waiting", "CONFIRMED": "Confirmed",
             "REJECTED": "Rejected", "EXPIRED": "Data deleted first"}
    scope = "all users" if data["scope"] == "everyone" else f"{data['generated_by']}'s own work"
    body = facts([("Period", f"{data['start']} to {data['end']}"), ("Covers", scope),
                  ("Build", f"DocumentLab {data['app_version']} · rule set {data['ruleset_version']}")])
    rows = []
    for s in data["sections"].values():
        if "total" not in s:
            continue
        results = ", ".join(f"{words[k]} {s['by_status'][k]}" for k in STATUS_ORDER if s["by_status"].get(k)) or "—"
        reviews = ", ".join(f"{words[k]} {s['reviews'][k]}" for k in REVIEW_ORDER if s.get("reviews", {}).get(k)) or "—"
        rows.append([s["label"], str(s["total"]), results, reviews if "reviews" in s else "n/a"])
    body += "<h2>Work done</h2>" + table(["Area", "Total", "Results", "Reviews"], rows)
    lab = data["sections"]["test_lab"]
    last = lab["last_run"]
    body += "<h2>Testing Laboratory</h2>" + facts([
        ("Completed runs", str(lab["runs"])), ("Runs with failures or errors", str(lab["runs_with_failures"])),
        ("Latest run", f"{last['reference']}: {last['passed']} of {last['total']} passed" if last else "None in this period")])
    body += "<h2>Rules that most often failed or asked for review</h2>" + (
        table(["Rule", "Area", "Failed", "Needed review"],
              [[f"{r['name']} ({r['code']})", r["module"], str(r["failed"]), str(r["review"])] for r in data["rules"]])
        if data["rules"] else "<p>No failures or reviews in this period.</p>")
    body += f'<p class="small muted">Counts only; this report contains no personal data. {esc(AUTHENTICITY_NOTE)}</p>'
    return render("Activity summary", body, subtitle=f"{data['start']} to {data['end']}")
