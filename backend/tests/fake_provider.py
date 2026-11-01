"""Test-only stand-ins for an authorised provider's adapter. Never configured outside the test suite."""
import time

from core.verification.base import ERROR, MATCH, NO_MATCH, ProviderResult, SsnVerificationProvider

# Invented test data: the provider "knows" one person.
KNOWN = {"number": "212345678", "first_name": "ZAWADI", "last_name": "EXAMPLE", "birth_date": "1980-02-03"}


class FakeProvider(SsnVerificationProvider):
    name = "Test provider"
    received: list = []

    def verify_ssn(self, request):
        FakeProvider.received.append(request)
        if request.number != KNOWN["number"]:
            return ProviderResult(NO_MATCH, ["number"], reference="T-2")
        wrong = [f for f in ("first_name", "last_name") if getattr(request, f).upper() != KNOWN[f]]
        if request.birth_date.isoformat() != KNOWN["birth_date"]:
            wrong.append("birth_date")
        return ProviderResult(NO_MATCH if wrong else MATCH, wrong, reference="T-1")


class BrokenProvider(SsnVerificationProvider):
    name = "Broken provider"

    def verify_ssn(self, request):
        raise ConnectionError("network down")


class SlowProvider(SsnVerificationProvider):
    name = "Slow provider"
    timeout_seconds = 0.2

    def verify_ssn(self, request):
        time.sleep(1)
        return ProviderResult(MATCH)


class ConfusedProvider(SsnVerificationProvider):
    name = "Confused provider"

    def verify_ssn(self, request):
        return {"ok": True}  # not a ProviderResult


class NeedsCredentials(SsnVerificationProvider):
    name = "Needs credentials"

    def __init__(self):
        raise RuntimeError("PROVIDER_API_KEY is not set")

    def verify_ssn(self, request):  # pragma: no cover
        return ProviderResult(ERROR)
