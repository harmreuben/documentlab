"""Loads the configured provider adapter, if there is one."""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.utils.module_loading import import_string

from .base import SsnVerificationProvider


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[SsnVerificationProvider | None, str]:
    if not path:
        return None, ""
    try:
        cls = import_string(path)
    except ImportError as exc:
        return None, f"The provider adapter '{path}' couldn't be loaded: {exc}"
    if not (isinstance(cls, type) and issubclass(cls, SsnVerificationProvider)):
        return None, f"'{path}' isn't an SsnVerificationProvider."
    try:
        return cls(), ""
    except Exception as exc:  # noqa: BLE001 - e.g. missing credentials in the environment
        return None, f"The provider adapter couldn't start: {exc}"


def ssn_provider() -> SsnVerificationProvider | None:
    return _load(settings.SSN_VERIFICATION_PROVIDER)[0]


def describe() -> dict:
    provider, error = _load(settings.SSN_VERIFICATION_PROVIDER)
    return {"available": provider is not None, "name": provider.name if provider else None, "error": error}
