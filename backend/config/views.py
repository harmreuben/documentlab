from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(responses={200: dict, 503: dict})
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Real check: runs a query against the database instead of always saying OK."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_status = "ok"
    except Exception:  # pragma: no cover - only when the database is down
        db_status = "unavailable"
    code = 200 if db_status == "ok" else 503
    return Response({"status": db_status, "version": settings.APP_VERSION, "database": db_status}, status=code)
