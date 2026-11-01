"""Results that already needed review before Phase 9 join the review queue."""
from django.db import migrations


def queue(apps, schema_editor):
    apps.get_model("barcode_decoder", "BarcodeAnalysis").objects.filter(
        status="REVIEW_REQUIRED", review_state="").update(review_state="PENDING")


class Migration(migrations.Migration):
    dependencies = [("barcode_decoder", "0002_barcodeanalysis_review_note_and_more")]
    operations = [migrations.RunPython(queue, migrations.RunPython.noop)]
