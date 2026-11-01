"""Dashboard summary. Every number comes from a database query - nothing is hardcoded.

Administrators see system-wide figures. Everyone else sees only their own activity.
Figures for modules that do not exist yet are returned as null, never as zero, so the
frontend can show "not available yet" instead of a misleading 0.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.reviews.services import pending_count
from apps.audit.models import AuditEvent
from apps.barcode_decoder.models import DecodedBarcode
from apps.barcode_generator.models import GeneratedBarcode
from apps.document_analysis.models import DocumentAnalysis

from .modules import MODULES

ACTIVITY_DAYS = 14


class DashboardSummaryView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        user = request.user
        is_admin = user.role == Role.ADMINISTRATOR
        now = timezone.now()
        today = timezone.localdate()

        events = AuditEvent.objects.all() if is_admin else AuditEvent.objects.filter(user=user)
        barcodes = GeneratedBarcode.objects.all() if is_admin else GeneratedBarcode.objects.filter(created_by=user)
        documents = DocumentAnalysis.objects.all() if is_admin else DocumentAnalysis.objects.filter(created_by=user)
        decoded = DecodedBarcode.objects.filter(valid=True)
        if not is_admin:
            decoded = decoded.filter(analysis__created_by=user)

        # Activity per day for the last 14 days, including days with no events.
        start = today - timedelta(days=ACTIVITY_DAYS - 1)
        rows = (events.filter(created_at__date__gte=start)
                .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
                .values("day").annotate(n=Count("id")))
        per_day = {r["day"]: r["n"] for r in rows}
        activity = [{"date": (start + timedelta(days=i)).isoformat(),
                     "events": per_day.get(start + timedelta(days=i), 0)}
                    for i in range(ACTIVITY_DAYS)]

        recent = [
            {"id": e.id, "created_at": e.created_at, "username": e.username, "action": e.action}
            for e in events[:8]
        ]

        users = None
        if is_admin:
            by_role = dict(User.objects.filter(is_active=True).values_list("role").annotate(n=Count("id")))
            users = {
                "total": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "by_role": {r.value: by_role.get(r.value, 0) for r in Role},
            }

        return Response({
            "scope": "system" if is_admin else "personal",
            "version": settings.APP_VERSION,
            "generated_at": now,
            "counts": {
                "events_24h": events.filter(created_at__gte=now - timedelta(hours=24)).count(),
                "logins_7d": events.filter(action="auth.login", created_at__gte=now - timedelta(days=7)).count(),
                "failed_logins_7d": (AuditEvent.objects.filter(action="auth.login_failed",
                                                               created_at__gte=now - timedelta(days=7)).count()
                                     if is_admin else None),
                "barcodes_generated": barcodes.count(),
                "barcodes_failed_verification": barcodes.filter(verification_status="FAIL").count(),
                "barcodes_decoded": decoded.count(),
                "documents_processed": documents.count(),
                # Not built yet - null until its phase is finished.
                "pending_reviews": pending_count(user),
            },
            "users": users,
            "activity": activity,
            "recent_activity": recent,
            "modules": MODULES,
        })
