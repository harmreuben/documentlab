"""Asking an authorised provider whether an SSN belongs to the named person. Off until configured."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from core.identity import ssn
from core.rules.catalogue import RULESET_VERSION
from core.verification import registry
from core.verification.base import (
    ERROR,
    MATCH,
    NO_MATCH,
    Consent,
    ProviderResult,
    SsnRequest,
)

from .models import SsnVerification

STATUS = {MATCH: "PASS", NO_MATCH: "FAIL", ERROR: "UNAVAILABLE"}
FIELD_WORDS = {"number": "number", "first_name": "first name", "last_name": "last name", "birth_date": "date of birth"}


class NotConfigured(Exception):
    pass


class InvalidNumber(ValueError):
    pass


def _ask(provider, request: SsnRequest) -> ProviderResult:
    """Call the adapter with a time limit. Anything but a clear answer counts as unavailable."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        result = pool.submit(provider.verify_ssn, request).result(timeout=provider.timeout_seconds)
    except FutureTimeout:
        return ProviderResult(ERROR, message=f"The provider didn't answer within {provider.timeout_seconds:g} seconds.")
    except Exception as exc:  # noqa: BLE001 - the adapter is outside DocumentLab's control
        return ProviderResult(ERROR, message=f"The provider adapter failed ({type(exc).__name__}).")
    finally:
        pool.shutdown(wait=False)
    if not isinstance(result, ProviderResult) or result.outcome not in STATUS:
        return ProviderResult(ERROR, message="The provider adapter gave an answer DocumentLab doesn't understand.")
    return result


def summary(record: SsnVerification) -> str:
    if record.outcome == MATCH:
        return (f"{record.provider}'s records match the number, name and date of birth given. This confirms the "
                "combination with the provider; it doesn't prove who is presenting it.")
    if record.outcome == NO_MATCH:
        fields = ", ".join(FIELD_WORDS.get(f, f) for f in record.mismatched) or "the details given"
        return (f"{record.provider}'s records don't match: {fields}. Check for typing errors or a name change "
                "before drawing any conclusion.")
    return f"No answer from {record.provider}, so ownership wasn't checked. {record.provider_message}".strip()


def verify(*, user, number: str, first_name: str, last_name: str, birth_date, consent: Consent) -> SsnVerification:
    provider = registry.ssn_provider()
    if provider is None:
        raise NotConfigured("No authorised verification provider is configured.")
    checked = ssn.check(number)
    if not checked.format_valid:
        problem = next((c.detail for c in checked.checks if c.status == "FAIL"), "The format isn't valid.")
        raise InvalidNumber(f"Fix the number's format first: {problem}")
    digits = "".join(ch for ch in number if ch.isdigit())
    result = _ask(provider, SsnRequest(digits, first_name.strip(), last_name.strip(), birth_date, consent))
    return SsnVerification.objects.create(
        created_by=user, masked=checked.masked, provider=provider.name[:80], outcome=result.outcome,
        status=STATUS[result.outcome], mismatched=[m for m in result.mismatched if m in FIELD_WORDS],
        deceased=result.deceased, provider_reference=result.reference[:80], provider_message=result.message[:200],
        consent_method=consent.method, consent_reference=consent.reference[:80], consent_signed_on=consent.signed_on,
        purpose=consent.purpose, ruleset_version=RULESET_VERSION,
    )
