"""Production. Every secret comes from the environment or .env, never from code.

Run with:  $env:DJANGO_SETTINGS_MODULE = "config.settings.prod"   (see docs/DEPLOYMENT.md)
`python manage.py check --deploy` lists anything still unsafe.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import FRONTEND_DIST, MIDDLEWARE, SECRET_KEY, env

DEBUG = False
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production. See docs/DEPLOYMENT.md.")

# PostgreSQL for several users, e.g. postgres://user:pass@localhost:5432/documentlab
# (sqlite:///C:/Projects/documentlab/backend/db.sqlite3 works for one person on one PC; the security page warns.)
DATABASES = {"default": env.db("DATABASE_URL")}

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- HTTPS (encryption in transit) ---
# DJANGO_ALLOW_HTTP=true is only for trying production mode on one PC without a certificate.
ALLOW_HTTP = env.bool("DJANGO_ALLOW_HTTP", default=False)
SECURE_SSL_REDIRECT = not ALLOW_HTTP
SESSION_COOKIE_SECURE = not ALLOW_HTTP
CSRF_COOKIE_SECURE = not ALLOW_HTTP
SECURE_HSTS_SECONDS = 0 if ALLOW_HTTP else 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = not ALLOW_HTTP
if env.bool("DJANGO_BEHIND_HTTPS_PROXY", default=False):
    # A reverse proxy (e.g. Caddy) handles the certificate and tells Django the original request was HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# --- One server for the API and the website ---
# WhiteNoise serves Django's static files and the built React app; nothing else needs installing.
# WhiteNoise answers file requests itself and skips everything after it, so it goes *after* the security
# headers middleware: every file, including the website's own index page, gets the same protective headers.
_HEADERS = MIDDLEWARE.index("apps.system.middleware.SecurityHeadersMiddleware")
MIDDLEWARE = [*MIDDLEWARE[:_HEADERS + 1], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[_HEADERS + 1:]]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
# The index page is served by Django (apps.system.views.frontend) so it is never cached by proxies and always
# picks up a new build; WhiteNoise serves the hashed assets, which can be cached for a long time.
WHITENOISE_INDEX_FILE = False
WHITENOISE_ALLOW_ALL_ORIGINS = False  # files are for this site only
# Vite names built files like assets/index-B3x9kQ2p.js: the name changes whenever the content does,
# so browsers may keep them forever without asking again.
WHITENOISE_IMMUTABLE_FILE_TEST = r"/assets/[^/]+-[0-9A-Za-z_-]{8,}\.(js|css|woff2?|svg|png)$"
SERVE_FRONTEND = True

# Errors go to logs\documentlab.log (personal data is redacted before writing); nothing is shown to visitors.
ADMINS = []
