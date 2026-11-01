"""Temporary account lock after repeated failed sign-ins.

The sign-in throttle limits attempts per computer. This limits attempts per account, so guessing a
password from many computers doesn't work either. Failures are counted from the audit log, so the
lock survives a server restart and needs no extra table.

The same message is given whether or not the username exists, so the lock can't be used to find
out which accounts exist.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditEvent


def _window():
    return timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)


def failures(username: str) -> list:
    """Failed sign-ins for this username in the window, since its last successful sign-in."""
    since = timezone.now() - _window()
    last_ok = (AuditEvent.objects.filter(action="auth.login", username__iexact=username, created_at__gte=since)
               .order_by("-created_at").values_list("created_at", flat=True).first())
    qs = AuditEvent.objects.filter(action="auth.login_failed", username__iexact=username, created_at__gte=last_ok or since)
    return list(qs.order_by("created_at").values_list("created_at", flat=True))


def locked_until(username: str):
    """When the lock ends, or None if the account isn't locked."""
    attempts = settings.LOGIN_LOCKOUT_ATTEMPTS
    if not attempts or not username:
        return None
    times = failures(username)
    if len(times) < attempts:
        return None
    until = times[-1] + _window()
    return until if until > timezone.now() else None


def message(until) -> str:
    minutes = max(1, round((until - timezone.now()).total_seconds() / 60))
    return (f"Too many failed sign-ins for this account. Try again in {minutes} minute{'s' if minutes != 1 else ''}, "
            "or ask an administrator to reset the password.")
