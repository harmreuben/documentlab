from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "username", "action", "object_type", "object_id", "ip_address"]
    list_filter = ["action"]
    search_fields = ["username", "action", "object_id"]

    # Viewing only: no adding, editing or deleting from the admin site.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
