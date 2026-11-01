"""Creates or refreshes the standard synthetic fixtures.

    python manage.py load_test_fixtures
"""
from django.core.management.base import BaseCommand

from apps.test_lab.services import load_builtins


class Command(BaseCommand):
    help = "Create or refresh the Testing Laboratory's standard synthetic fixtures."

    def handle(self, *args, **options):
        created, updated = load_builtins()
        self.stdout.write(self.style.SUCCESS(f"Standard fixtures: {created} added, {updated} refreshed."))
