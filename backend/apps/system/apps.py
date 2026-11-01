from django.apps import AppConfig


class SystemConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.system"
    label = "system"
    verbose_name = "System and security"

    def ready(self):
        from . import checks  # noqa: F401  (registers the production checks)
