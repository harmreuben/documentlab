from django.contrib import admin

from .models import DocumentAnalysis


@admin.register(DocumentAnalysis)
class DocumentAnalysisAdmin(admin.ModelAdmin):
    # Personal fields are deliberately not shown in the admin site.
    list_display = ["reference", "detected_type", "status", "created_by", "created_at", "expires_at", "purged_at"]
    list_filter = ["status", "detected_type"]
    fields = ["reference", "detected_type", "status", "created_by", "created_at", "expires_at", "purged_at", "purge_reason"]
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
