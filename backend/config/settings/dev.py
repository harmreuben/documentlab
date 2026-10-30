"""Local development on your Windows PC."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-change-me")
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# The Vite dev server (Phase 4) runs on port 5173 and proxies /api to Django.
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
