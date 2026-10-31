"""The two entry points: check() validates, generate() renders and verifies."""
from __future__ import annotations

from dataclasses import dataclass, field

from .guards import IDENTITY_LAYOUT_MESSAGE, identity_layout_reason
from .issues import Issues
from .options import resolve_options
from .render import Rendered, render
from .schemas import TEXT_SCHEMA, build_payload, get_schema
from .symbologies import Symbology, get_symbology
from .verify import Verification, verify


@dataclass
class CheckResult:
    ok: bool
    format: str
    schema: str
    expected_decode: str = ""
    check_digit: str | None = None
    options: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    blocked: bool = False  # True when the identity-layout guard refused the payload
    render_input: str = ""
    symbology: Symbology | None = None

    def as_dict(self) -> dict:
        return {"ok": self.ok, "format": self.format, "schema": self.schema,
                "expected_decode": self.expected_decode, "check_digit": self.check_digit,
                "options": self.options, "errors": self.errors, "warnings": self.warnings,
                "blocked": self.blocked}


@dataclass
class GenerateResult:
    check: CheckResult
    output: Rendered | None = None
    verification: Verification | None = None

    @property
    def ok(self) -> bool:
        return self.check.ok and self.output is not None


def _finish(result: CheckResult, issues: Issues) -> CheckResult:
    result.errors = [i.as_dict() for i in issues.errors]
    result.warnings = [i.as_dict() for i in issues.warnings]
    result.ok = issues.ok
    return result


def check(format_key: str, payload: str | None = None, options: dict | None = None,
          schema_id: str = TEXT_SCHEMA, fields: dict | None = None, _issues: Issues | None = None) -> CheckResult:
    issues = _issues or Issues()
    schema_id = schema_id or TEXT_SCHEMA
    result = CheckResult(ok=False, format=format_key, schema=schema_id)

    symbology = get_symbology(format_key)
    if symbology is None:
        issues.error("format", "Choose a supported barcode format.")
        return _finish(result, issues)
    result.symbology = symbology

    schema = get_schema(schema_id)
    if schema is None:
        issues.error("schema", "Choose a supported payload schema.")
        return _finish(result, issues)
    if schema.structured and not symbology.structured:
        issues.error("schema", f"{symbology.name} can only hold plain text. Use QR Code or PDF417 for structured data.")
        return _finish(result, issues)

    if schema.structured:
        text = build_payload(schema, fields or {}, issues)
        if not issues.ok:
            result.options = resolve_options(symbology.family, options, issues)
            return _finish(result, issues)
    else:
        text = payload or ""
        if symbology.family == "linear" or not text.strip():
            text = text.strip()

    if text and identity_layout_reason(text):
        issues.error("payload", IDENTITY_LAYOUT_MESSAGE)
        result.blocked = True
        return _finish(result, issues)

    result.render_input, result.expected_decode, result.check_digit = symbology.validate(text, issues)
    result.options = resolve_options(symbology.family, options, issues)
    return _finish(result, issues)


def generate(format_key: str, payload: str | None = None, options: dict | None = None,
             schema_id: str = TEXT_SCHEMA, fields: dict | None = None, run_verification: bool = True) -> GenerateResult:
    issues = Issues()
    checked = check(format_key, payload, options, schema_id, fields, _issues=issues)
    if not checked.ok:
        return GenerateResult(checked)

    output = render(checked.symbology, checked.render_input, checked.options, issues)
    _finish(checked, issues)  # rendering can add warnings (PDF417 columns) or errors (data too long)
    if output is None or not checked.ok:
        return GenerateResult(checked)

    verification = verify(checked.symbology, output.png, checked.expected_decode) if run_verification else None
    return GenerateResult(checked, output, verification)
