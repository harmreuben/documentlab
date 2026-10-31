from django.contrib import admin

from .models import GeneratedBarcode, GenerationBatch


@admin.register(GeneratedBarcode)
class GeneratedBarcodeAdmin(admin.ModelAdmin):
    list_display = ["test_reference", "format", "schema_id", "verification_status", "created_by", "created_at"]
    list_filter = ["format", "verification_status"]
    search_fields = ["test_reference", "label"]
    readonly_fields = [f.name for f in GeneratedBarcode._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(GenerationBatch)
class GenerationBatchAdmin(admin.ModelAdmin):
    list_display = ["id", "source_name", "total_rows", "succeeded", "failed", "created_by", "created_at"]
    readonly_fields = [f.name for f in GenerationBatch._meta.fields]

    def has_add_permission(self, request):
        return False
