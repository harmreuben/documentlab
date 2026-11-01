"""Runs DocumentLab for real use with Waitress, a production web server that works on Windows.

    $env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
    python manage.py serve                    # http://127.0.0.1:8000, this computer only
    python manage.py serve --host 0.0.0.0     # reachable from other computers (use HTTPS: docs/DEPLOYMENT.md)

`runserver` is for development only; it isn't built to be secure or to handle several users.
"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Serve DocumentLab with the Waitress production server."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--threads", type=int, default=8)

    def handle(self, *args, **opts):
        if settings.DEBUG:
            raise CommandError("serve is for production settings. Set DJANGO_SETTINGS_MODULE=config.settings.prod first, "
                               "or use runserver for development.")
        call_command("check", deploy=True, fail_level="ERROR")
        from waitress import serve

        from config.wsgi import application
        url = f"http://{'localhost' if opts['host'] in ('127.0.0.1', '0.0.0.0') else opts['host']}:{opts['port']}"
        self.stdout.write(self.style.SUCCESS(f"DocumentLab {settings.APP_VERSION} is running at {url}  (Ctrl+C to stop)"))
        proxy = {}
        if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
            # Only the HTTPS proxy on this same computer is trusted to say a request arrived over HTTPS.
            proxy = {"trusted_proxy": "127.0.0.1", "trusted_proxy_headers": {"x-forwarded-proto", "x-forwarded-for"}}
        serve(application, host=opts["host"], port=opts["port"], threads=opts["threads"], ident="DocumentLab", **proxy)
