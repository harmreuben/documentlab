from django.contrib import admin

from .models import BarcodeAnalysis


@admin.register(BarcodeAnalysis)
class BarcodeAnalysisAdmin(admin.ModelAdmin):
    list_display = ["reference", "status", "created_by", "created_at", "sensitive"]
    list_filter = ["status", "sensitive"]
    search_fields = ["reference"]
    readonly_fields = [f.name for f in BarcodeAnalysis._meta.fields]

    def has_add_permission(self, request):
        return False
