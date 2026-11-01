from datetime import date, timedelta

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import RoleAwareDefault
from apps.audit.services import record as audit

from .builders import summary, summary_csv, summary_pdf

MAX_DAYS = 366


def _date(value: str | None, default: date) -> date:
    if not value:
        return default
    return date.fromisoformat(value)


class SummaryView(APIView):
    permission_classes = [RoleAwareDefault]

    @extend_schema(parameters=[OpenApiParameter("start", str), OpenApiParameter("end", str),
                               OpenApiParameter("type", str, enum=["json", "csv", "pdf"])], responses={200: dict})
    def get(self, request):
        today = date.today()
        try:
            end = _date(request.query_params.get("end"), today)
            start = _date(request.query_params.get("start"), end - timedelta(days=29))
        except ValueError:
            return Response({"detail": "Use dates like 2026-11-01."}, status=status.HTTP_400_BAD_REQUEST)
        if start > end:
            return Response({"detail": "The start date must be on or before the end date."}, status=status.HTTP_400_BAD_REQUEST)
        if (end - start).days >= MAX_DAYS:
            return Response({"detail": "Choose a period of one year or less."}, status=status.HTTP_400_BAD_REQUEST)
        kind = request.query_params.get("type", "json")
        if kind not in ("json", "csv", "pdf"):
            return Response({"detail": "Choose json, csv or pdf."}, status=status.HTTP_400_BAD_REQUEST)
        data = summary(request.user, start, end)
        if kind == "json":
            return Response(data)
        audit(request, "report.downloaded", None, {"report": "summary", "type": kind, "start": data["start"], "end": data["end"]})
        name = f"documentlab-summary-{data['start']}-to-{data['end']}.{kind}"
        body, content_type = (summary_csv(data), "text/csv; charset=utf-8") if kind == "csv" else (summary_pdf(data), "application/pdf")
        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
