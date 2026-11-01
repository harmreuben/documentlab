"""Extra checks for `python manage.py check --deploy`, on top of Django's own."""
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from .status import secret_key_problem


@register(Tags.security, deploy=True)
def documentlab_deploy_checks(app_configs, **kwargs):
    problems = []
    if (reason := secret_key_problem()) and not settings.DEBUG:
        problems.append(Error(reason, hint="Generate a key (docs/DEPLOYMENT.md) and set DJANGO_SECRET_KEY.", id="documentlab.E001"))
    if getattr(settings, "SERVE_FRONTEND", False) and not (settings.FRONTEND_DIST / "index.html").exists():
        problems.append(Error("The React app isn't built, so the website can't be served.",
                              hint="Run 'npm run build' in the frontend folder.", id="documentlab.E002"))
    if getattr(settings, "ALLOW_HTTP", False):
        problems.append(Warning("DJANGO_ALLOW_HTTP is on: passwords and documents travel unencrypted.",
                                hint="Only use this to try production mode on one PC. Use HTTPS for real use.",
                                id="documentlab.W001"))
    if settings.DATABASES["default"]["ENGINE"].endswith("sqlite3") and not settings.DEBUG:
        problems.append(Warning("SQLite is in use. It suits one person on one computer, not several users at once.",
                                hint="Set DATABASE_URL to a PostgreSQL database.", id="documentlab.W002"))
    if not 0 < settings.SESSION_IDLE_MINUTES <= 60:
        problems.append(Warning("The idle sign-out is off or longer than an hour.",
                                hint="Set SESSION_IDLE_MINUTES between 5 and 60.", id="documentlab.W003"))
    return problems
