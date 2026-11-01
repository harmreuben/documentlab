"""Results that already needed review before Phase 9 join the review queue, unless their data is gone."""
from django.db import migrations


def queue(apps, schema_editor):
    model = apps.get_model("document_analysis", "DocumentAnalysis")
    waiting = model.objects.filter(status="REVIEW_REQUIRED", review_state="")
    waiting.filter(purged_at__isnull=False).update(review_state="EXPIRED")
    waiting.filter(purged_at__isnull=True).update(review_state="PENDING")


class Migration(migrations.Migration):
    dependencies = [("document_analysis", "0002_documentanalysis_review_note_and_more")]
    operations = [migrations.RunPython(queue, migrations.RunPython.noop)]
