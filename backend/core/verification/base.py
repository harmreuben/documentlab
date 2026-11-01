"""The contract between DocumentLab and an external SSN verification provider.

DocumentLab ships no provider. Access to services that confirm who an SSN belongs to (for example
the Social Security Administration's eCBSV) is limited to eligible organisations that have signed
an agreement, and each requires the number holder's written consent. An organisation with that
access writes a small adapter class that implements `SsnVerificationProvider` using its provider's
own API and credentials, and names it in SSN_VERIFICATION_PROVIDER. See docs/SECURITY.md.

DocumentLab's side of the bargain:
- it never calls a provider without a recorded consent;
- it sends only the number, name and date of birth, and stores none of them in full;
- it reports exactly what the provider said, and treats errors and timeouts as "unavailable".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

MATCH, NO_MATCH, ERROR = "match", "no_match", "error"

PURPOSES = {
    "account_opening": "Opening an account or service the person applied for",
    "employment": "Employment or payroll",
    "credit": "A credit application the person made",
    "other_consented": "Another purpose stated on the person's signed consent",
}
CONSENT_METHODS = {"signed_paper": "Signed paper form", "electronic_signature": "Electronic signature"}


@dataclass(frozen=True)
class Consent:
    method: str          # a key of CONSENT_METHODS
    reference: str       # the organisation's identifier for the signed consent form
    signed_on: date
    purpose: str         # a key of PURPOSES


@dataclass(frozen=True)
class SsnRequest:
    number: str          # nine digits, format already checked
    first_name: str
    last_name: str
    birth_date: date
    consent: Consent


@dataclass
class ProviderResult:
    outcome: str                                          # MATCH, NO_MATCH or ERROR
    mismatched: list[str] = field(default_factory=list)   # names of fields that didn't match, never values
    reference: str = ""                                   # the provider's transaction reference, for audits
    message: str = ""                                     # the provider's own short explanation
    deceased: bool | None = None                          # some providers report a death record


class SsnVerificationProvider(ABC):
    name: str = "Unnamed provider"
    timeout_seconds: float = 20

    @abstractmethod
    def verify_ssn(self, request: SsnRequest) -> ProviderResult:
        """Ask the provider. Return ERROR (don't raise) for anything other than a clear answer."""
