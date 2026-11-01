"""The validation rule catalogue, with test coverage measured from the Testing Laboratory."""
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import RoleAwareDefault
from apps.test_lab.models import CaseResult, TestRun
from core.rules import coverage
from core.rules.catalogue import MODULES, RULES, RULESET_VERSION, SEVERITY


def latest_cases() -> tuple[list[coverage.CaseView], TestRun | None]:
    """The most recent result of every active fixture, from finished runs."""
    seen, views = set(), []
    qs = (CaseResult.objects.filter(fixture__active=True, run__status=TestRun.COMPLETE)
          .select_related("run").order_by("fixture_id", "-run__created_at", "-id"))
    for case in qs:
        if case.fixture_id in seen:
            continue
        seen.add(case.fixture_id)
        views.append(coverage.CaseView(case.fixture_id, case.fixture_name, case.module, case.expected or {}, case.actual))
    latest = TestRun.objects.filter(status=TestRun.COMPLETE).order_by("-created_at", "-id").first()
    return views, latest


def rule_dict(rule, cov) -> dict:
    return {
        "code": rule.code, "name": rule.name, "module": rule.module, "module_label": MODULES[rule.module],
        "category": rule.category, "checks": rule.checks, "outcomes": rule.outcomes, "reference": rule.reference,
        "version": rule.version, "since": rule.since,
        "changes": [{"version": v, "app_version": a, "note": n} for v, a, n in rule.changes],
        "parameters": rule.parameters, "keys": list(rule.match_keys),
        "severity": rule.severity, "severity_label": SEVERITY[rule.severity], "coverage": cov.as_dict(),
    }


class RulesView(APIView):
    permission_classes = [RoleAwareDefault]

    @extend_schema(responses={200: dict})
    def get(self, request):
        cases, latest = latest_cases()
        measured = coverage.measure(cases)
        rules = [rule_dict(r, measured[r.code]) for r in RULES]
        summary = {level: sum(1 for r in rules if r["coverage"]["level"] == level) for level in coverage.LEVEL_LABELS}
        return Response({
            "ruleset_version": RULESET_VERSION,
            "modules": [{"key": k, "label": v} for k, v in MODULES.items()],
            "severities": [{"key": k, "label": v} for k, v in SEVERITY.items()],
            "coverage_levels": [{"key": k, "label": v} for k, v in coverage.LEVEL_LABELS.items()],
            "coverage_summary": summary,
            "measured_from": {"fixtures": len(cases),
                              "latest_run": {"id": latest.pk, "reference": latest.reference,
                                             "at": latest.created_at} if latest else None},
            "rules": rules,
        })
