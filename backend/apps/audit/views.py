from rest_framework import serializers, viewsets

from apps.accounts.permissions import IsAdministrator

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "created_at", "username", "action", "object_type", "object_id",
                  "ip_address", "user_agent", "metadata"]
        read_only_fields = fields


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Audit log - administrators only, read-only. Filter with ?action=auth.login or ?username=alice."""

    serializer_class = AuditEventSerializer
    permission_classes = [IsAdministrator]

    def get_queryset(self):
        qs = AuditEvent.objects.all()
        action = self.request.query_params.get("action")
        username = self.request.query_params.get("username")
        if action:
            qs = qs.filter(action=action)
        if username:
            qs = qs.filter(username=username)
        return qs
