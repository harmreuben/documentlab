"""How well each rule is covered by the Testing Laboratory, measured from real results.

For each rule we look at the latest result of every active fixture and record:
- exercised: the fixtures whose run produced this rule's check, and which results it gave;
- asserted:  the fixtures whose expected result names this rule's check explicitly.

A blocking rule is fully covered when fixtures have seen it both pass and fail; a review rule when it has
been seen passing and asking for review. Seeing only one side means the other branch is untested.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalogue import FAIL, PASS, REVIEW, RULES, Rule

FULL, PARTIAL, NONE, OUTSIDE = "full", "partial", "none", "outside"
LEVEL_LABELS = {FULL: "Fully tested", PARTIAL: "Partly tested", NONE: "Not tested",
                OUTSIDE: "Outside the Testing Laboratory"}


@dataclass
class CaseView:
    fixture_id: int
    fixture_name: str
    module: str
    expected: dict
    actual: dict | None


@dataclass
class Coverage:
    level: str
    statuses: list[str] = field(default_factory=list)
    exercised_by: list[dict] = field(default_factory=list)
    asserted_by: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"level": self.level, "label": LEVEL_LABELS[self.level], "statuses": self.statuses,
                "exercised_by": self.exercised_by, "asserted_by": self.asserted_by}


def _needed(rule: Rule) -> set[str]:
    if rule.severity == "blocking":
        return {PASS, FAIL}
    if rule.severity == "review":
        return {PASS, REVIEW} if PASS in rule.outcomes else {REVIEW}
    return set(rule.outcomes)


def measure(cases: list[CaseView]) -> dict[str, Coverage]:
    results: dict[str, Coverage] = {}
    for rule in RULES:
        if not rule.lab_module:
            results[rule.code] = Coverage(OUTSIDE)
            continue
        seen: set[str] = set()
        exercised, asserted = [], []
        for case in cases:
            if case.module != rule.lab_module:
                continue
            ref = {"id": case.fixture_id, "name": case.fixture_name}
            got = {k: v for k, v in ((case.actual or {}).get("checks") or {}).items() if rule.produces(k)}
            if got:
                seen.update(got.values())
                exercised.append({**ref, "statuses": sorted(set(got.values()))})
            if any(rule.produces(k) for k in (case.expected.get("checks") or {})):
                asserted.append(ref)
        needed = _needed(rule)
        level = NONE if not seen else FULL if needed <= seen else PARTIAL
        results[rule.code] = Coverage(level, sorted(seen), exercised, asserted)
    return results
