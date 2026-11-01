"""Security middleware: response headers and the idle-session sign-out."""
from __future__ import annotations

import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse

# Only this site's own files may load. Inline styles are allowed because React sets a few
# `style` attributes (bar widths, colours); scripts are never inline.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
# The API documentation page loads its viewer from a CDN, so it keeps Django's defaults instead.
CSP_EXEMPT_PREFIXES = ("/api/docs/",)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(CSP_EXEMPT_PREFIXES):
            response.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("X-Content-Type-Options", "nosniff")
        # Also set by Django's clickjacking middleware, which files served by WhiteNoise never reach.
        response.setdefault("X-Frame-Options", "DENY")
        return response


class IdleTimeoutMiddleware:
    """Signs a user out after SESSION_IDLE_MINUTES without a request.

    Identity data is on screen in this application, so an unattended browser shouldn't stay signed in
    for the whole 8-hour session. API callers get a 401 with code "session_expired" so the app can
    send the person to the sign-in page with an explanation.
    """

    TOUCH_EVERY_SECONDS = 60  # don't rewrite the session on every request

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        limit = getattr(settings, "SESSION_IDLE_MINUTES", 0) * 60
        if limit and user is not None and user.is_authenticated:
            now = int(time.time())
            last = request.session.get("last_activity")
            if last is not None and now - last > limit:
                from apps.audit.services import record
                record(request, "auth.session_expired", user, {"idle_minutes": settings.SESSION_IDLE_MINUTES}, user=user)
                logout(request)
                if request.path.startswith("/api/"):
                    return JsonResponse({"detail": f"You were signed out after {settings.SESSION_IDLE_MINUTES} minutes "
                                                   "without activity. Sign in again to continue.",
                                         "code": "session_expired"}, status=401)
            elif last is None or now - last >= self.TOUCH_EVERY_SECONDS:
                request.session["last_activity"] = now
        return self.get_response(request)
