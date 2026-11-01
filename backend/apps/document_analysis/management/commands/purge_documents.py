"""Deletes personal data whose retention period has ended.

Run it on a schedule (for example daily with Windows Task Scheduler):
    python manage.py purge_documents

DocumentLab also runs this check on every Document Analysis request, so expired data is
never shown even if the schedule isn't set up.
"""
from django.core.management.base import BaseCommand

from apps.document_analysis.services import purge_expired


class Command(BaseCommand):
    help = "Delete identity-document data whose retention period has ended."

    def handle(self, *args, **options):
        count = purge_expired()
        self.stdout.write(self.style.SUCCESS(f"Deleted personal data from {count} record(s)."))
