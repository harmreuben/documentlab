"""Security hardening: headers, idle sign-out, account lock, deployment checks, serving, backups."""
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.system.checks import documentlab_deploy_checks

from .conftest import PASSWORD

BACKEND = Path(__file__).resolve().parent.parent


def test_security_headers_on_every_response(client_as):
    response = client_as(Role.READ_ONLY).get("/api/dashboard/summary/")
    assert "default-src 'self'" in response["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "camera=()" in response["Permissions-Policy"]
    assert "Content-Security-Policy" not in APIClient().get("/api/docs/")  # the API viewer loads from a CDN


def test_idle_sessions_are_signed_out(client_as, settings):
    settings.SESSION_IDLE_MINUTES = 30
    client = client_as(Role.ANALYST)
    assert client.get("/api/auth/me/").status_code == 200
    session = client.session
    session["last_activity"] = int(time.time()) - 31 * 60
    session.save()
    expired = client.get("/api/auth/me/")
    assert expired.status_code == 401 and expired.json()["code"] == "session_expired"
    assert client.get("/api/auth/me/").status_code == 403  # now simply signed out
    assert AuditEvent.objects.filter(action="auth.session_expired", username="analyst").exists()


def _login(username, password):
    cache.clear()  # the per-computer throttle is tested elsewhere; this tests the per-account lock
    client = APIClient(enforce_csrf_checks=False)
    return client.post("/api/auth/login/", {"username": username, "password": password}, format="json")


def test_accounts_lock_after_repeated_failures(make_user, settings):
    settings.LOGIN_LOCKOUT_ATTEMPTS, settings.LOGIN_LOCKOUT_MINUTES = 5, 15
    make_user("alice", Role.ANALYST)
    for _ in range(4):
        assert _login("alice", "wrong-password").status_code == 401
    assert _login("alice", PASSWORD).status_code == 200  # success clears the count
    for _ in range(5):
        _login("alice", "wrong-password")
    locked = _login("alice", PASSWORD)  # even the right password is refused while locked
    assert locked.status_code == 429 and "Too many failed sign-ins" in locked.json()["detail"]
    assert AuditEvent.objects.filter(action="auth.login_locked").count() == 1


def test_the_lock_message_doesnt_reveal_which_accounts_exist(db, settings):
    settings.LOGIN_LOCKOUT_ATTEMPTS = 3
    for _ in range(3):
        _login("nobody-here", "x")
    assert _login("nobody-here", "x").json()["detail"].startswith("Too many failed sign-ins")


def test_deploy_checks_catch_unsafe_settings(settings, tmp_path):
    settings.DEBUG, settings.SECRET_KEY = False, "dev-only-insecure-key-change-me"
    settings.SERVE_FRONTEND, settings.FRONTEND_DIST = True, tmp_path
    settings.ALLOW_HTTP = True
    ids = {p.id for p in documentlab_deploy_checks(None)}
    assert {"documentlab.E001", "documentlab.E002", "documentlab.W001", "documentlab.W002"} <= ids


def test_production_settings_pass_djangos_deploy_check(tmp_path):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.prod",
           "DJANGO_SECRET_KEY": "k" * 20 + "Zq8#w2!pL0vX9rT4yU6iO3aS7dF1gH5jK", "DJANGO_ALLOWED_HOSTS": "documentlab.example",
           "DATABASE_URL": f"sqlite:///{(tmp_path / 'db.sqlite3').as_posix()}"}
    result = subprocess.run([sys.executable, "manage.py", "check", "--deploy", "--fail-level", "CRITICAL"],
                            cwd=BACKEND, env=env, capture_output=True, text=True)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "security.W" not in output, output  # none of Django's own security warnings
    assert "documentlab.W002" in output        # the honest SQLite warning remains


def test_status_page_is_for_administrators(client_as):
    assert client_as(Role.ANALYST).get("/api/system/status/").status_code == 403
    data = client_as(Role.ADMINISTRATOR).get("/api/system/status/").json()
    items = {i["key"]: i for i in data["items"]}
    assert items["backups"]["status"] == "FAIL" and items["verification"]["status"] == "UNAVAILABLE"
    assert items["lockout"]["status"] == "PASS" and data["status"] == "FAIL"


def test_production_serves_the_built_app_for_page_addresses(client_as, settings, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    settings.FRONTEND_DIST = tmp_path
    reader = client_as(Role.READ_ONLY)
    settings.SERVE_FRONTEND = False
    assert reader.get("/documents/7").status_code == 404
    settings.SERVE_FRONTEND = True
    page = reader.get("/documents/7")
    assert page.status_code == 200 and b"id=root" in b"".join(page.streaming_content)
    assert page["Cache-Control"] == "no-cache"
    assert reader.get("/api/does-not-exist/").status_code == 404


def test_backups_are_consistent_checksummed_and_pruned(settings, tmp_path, db):
    source = tmp_path / "live.sqlite3"
    with sqlite3.connect(source) as conn:
        conn.execute("create table t (v text)")
        conn.execute("insert into t values ('kept')")
    settings.DATABASES = {**settings.DATABASES, "default": {**settings.DATABASES["default"], "NAME": str(source)}}
    settings.BACKUP_DIR, settings.BACKUP_KEEP = tmp_path / "backups", 2
    for _ in range(3):
        call_command("backup_data")
        time.sleep(1.05)  # backup folders are named to the second
    folders = sorted((tmp_path / "backups").glob("backup-*"))
    assert len(folders) == 2
    manifest = json.loads((folders[-1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contains_personal_data"] is True and manifest["files"][0]["name"] == "db.sqlite3"
    with sqlite3.connect(folders[-1] / "db.sqlite3") as copy:
        assert copy.execute("select v from t").fetchall() == [("kept",)]
    from apps.system.status import security_status
    assert next(i for i in security_status()["items"] if i["key"] == "backups")["status"] == "PASS"


def test_files_served_by_whitenoise_get_the_security_headers(client_as, settings, tmp_path):
    """Regression: WhiteNoise used to sit before the headers middleware, so '/' had no CSP or frame protection."""
    import importlib
    import os
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-1a2b3c.js").write_text("console.log(1)", encoding="utf-8")
    env = {"DJANGO_SECRET_KEY": "x" * 64, "DATABASE_URL": "sqlite:///:memory:", "DJANGO_ALLOWED_HOSTS": "testserver"}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        importlib.reload(importlib.import_module("config.settings.base"))
        prod = importlib.reload(importlib.import_module("config.settings.prod"))
    finally:
        for k, v in old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
    order = prod.MIDDLEWARE
    assert order.index("apps.system.middleware.SecurityHeadersMiddleware") < order.index("whitenoise.middleware.WhiteNoiseMiddleware")
    assert prod.WHITENOISE_INDEX_FILE is False and prod.WHITENOISE_ALLOW_ALL_ORIGINS is False

    settings.MIDDLEWARE, settings.WHITENOISE_ROOT, settings.WHITENOISE_INDEX_FILE = order, tmp_path, False
    settings.WHITENOISE_ALLOW_ALL_ORIGINS, settings.FRONTEND_DIST, settings.SERVE_FRONTEND = False, tmp_path, True
    client = client_as(Role.READ_ONLY)
    for path in ("/", "/assets/app-1a2b3c.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "default-src 'self'" in response["Content-Security-Policy"], path
        assert response["X-Frame-Options"] == "DENY", path
        assert "Access-Control-Allow-Origin" not in response, path
    assert client.get("/")["Cache-Control"] == "no-cache"


def test_the_sign_in_rate_limit_explains_itself(api, db):
    for _ in range(5):
        api.post("/api/auth/login/", {"username": "nobody", "password": "wrong-password-1"}, format="json")
    response = api.post("/api/auth/login/", {"username": "nobody", "password": "wrong-password-1"}, format="json")
    assert response.status_code == 429
    assert response.json()["detail"].startswith("Too many sign-in attempts from this computer. Wait ")
    assert response.json()["detail"].endswith("and try again.") and response["Retry-After"]
