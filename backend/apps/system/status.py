"""The security and readiness status shown to administrators, and used by `manage.py check --deploy`.

Each item is measured from the running configuration, never assumed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

PASS, REVIEW, FAIL, UNAVAILABLE = "PASS", "REVIEW_REQUIRED", "FAIL", "UNAVAILABLE"


def _item(key, label, status, detail, action=""):
    return {"key": key, "label": label, "status": status, "detail": detail, "action": action}


def latest_backup() -> dict | None:
    folder = settings.BACKUP_DIR
    if not folder.exists():
        return None
    manifests = sorted(folder.glob("*/manifest.json"))
    if not manifests:
        return None
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    data["folder"] = str(manifests[-1].parent)
    return data


def secret_key_problem() -> str | None:
    key = settings.SECRET_KEY or ""
    if not key:
        return "No secret key is set."
    if key.startswith(("dev-only", "test-only", "django-insecure")) or len(key) < 50 or len(set(key)) < 5:
        return "The secret key is a development key or too short (fewer than 50 characters)."
    return None


def security_status() -> dict:
    items = []
    debug = settings.DEBUG
    items.append(_item("debug", "Debug mode", FAIL if debug else PASS,
                       "On: error pages show code and settings to visitors." if debug else "Off.",
                       "Run with config.settings.prod." if debug else ""))
    problem = secret_key_problem()
    items.append(_item("secret_key", "Secret key", FAIL if problem else PASS, problem or "Set, long and random.",
                       "Generate one (see docs/DEPLOYMENT.md) and put it in .env as DJANGO_SECRET_KEY." if problem else ""))

    https = getattr(settings, "SECURE_SSL_REDIRECT", False) and getattr(settings, "SESSION_COOKIE_SECURE", False)
    items.append(_item("https", "HTTPS only", PASS if https else (REVIEW if not debug else FAIL),
                       "Plain HTTP is redirected and cookies are only sent over HTTPS." if https else
                       "Plain HTTP is allowed, so passwords and documents can be read on the network.",
                       "" if https else "Put DocumentLab behind HTTPS (docs/DEPLOYMENT.md) and remove DJANGO_ALLOW_HTTP."))

    hosts = settings.ALLOWED_HOSTS
    items.append(_item("allowed_hosts", "Allowed host names", PASS if hosts and "*" not in hosts else FAIL,
                       ", ".join(hosts) if hosts else "None set.",
                       "" if hosts and "*" not in hosts else "Set DJANGO_ALLOWED_HOSTS to this server's name or address."))

    engine = connection.vendor
    items.append(_item("database", "Database", PASS if engine == "postgresql" else REVIEW,
                       "PostgreSQL." if engine == "postgresql" else
                       f"{engine.capitalize()}: fine for one person on one computer, not for several users at once.",
                       "" if engine == "postgresql" else "Use PostgreSQL when more than one person works at the same time."))

    backup = latest_backup()
    if backup is None:
        items.append(_item("backups", "Backups", FAIL, "No backup has been made.",
                           "Run python manage.py backup_data, and schedule it daily."))
    else:
        made = datetime.fromisoformat(backup["created_at"])
        age = timezone.now() - made
        items.append(_item("backups", "Backups", PASS if age < timedelta(days=2) else REVIEW,
                           f"Latest: {timezone.localtime(made):%d %b %Y %H:%M} ({age.days} day{'s' if age.days != 1 else ''} ago).",
                           "" if age < timedelta(days=2) else "Schedule python manage.py backup_data to run daily."))

    idle = settings.SESSION_IDLE_MINUTES
    items.append(_item("idle", "Idle sign-out", PASS if 0 < idle <= 60 else REVIEW,
                       f"After {idle} minutes without activity." if idle else "Off: unattended browsers stay signed in.",
                       "" if 0 < idle <= 60 else "Set SESSION_IDLE_MINUTES between 5 and 60."))
    attempts = settings.LOGIN_LOCKOUT_ATTEMPTS
    items.append(_item("lockout", "Account lock", PASS if attempts else REVIEW,
                       f"{attempts} failed sign-ins lock the account for {settings.LOGIN_LOCKOUT_MINUTES} minutes."
                       if attempts else "Off.", "" if attempts else "Set LOGIN_LOCKOUT_ATTEMPTS (for example 5)."))
    items.append(_item("retention", "Identity data retention", PASS if settings.DOCUMENT_RETENTION_DAYS <= 90 else REVIEW,
                       f"Personal data is deleted {settings.DOCUMENT_RETENTION_DAYS} days after analysis.",
                       "" if settings.DOCUMENT_RETENTION_DAYS <= 90 else "Keep personal data only as long as you need it."))

    if settings.SERVE_FRONTEND:
        built = (settings.FRONTEND_DIST / "index.html").exists()
        items.append(_item("frontend", "Website build", PASS if built else FAIL,
                           "Built and served by Django." if built else "The React app isn't built.",
                           "" if built else "Run npm run build in the frontend folder."))

    from core.ocr import engine as ocr
    available, engine_name = ocr.status()
    items.append(_item("ocr", "Text recognition", PASS if available else REVIEW, engine_name,
                       "" if available else "Install Tesseract to read document images."))

    from core.verification import registry
    provider = registry.describe()
    items.append(_item("verification", "SSN verification provider",
                       PASS if provider["available"] else (FAIL if provider["error"] else UNAVAILABLE),
                       provider["error"] or (f"Connected: {provider['name']}." if provider["available"] else
                                             "Not configured. Ownership checks report Unavailable."),
                       "" if provider["available"] else "Only connect a provider your organisation is authorised to use."))

    worst = FAIL if any(i["status"] == FAIL for i in items) else REVIEW if any(i["status"] == REVIEW for i in items) else PASS
    return {"status": worst, "version": settings.APP_VERSION, "checked_at": timezone.now().isoformat(), "items": items}
