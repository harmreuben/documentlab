from django.apps import AppConfig


class TestLabConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.test_lab"
    label = "test_lab"
    verbose_name = "Testing Laboratory"
