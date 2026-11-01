import io

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import HasRole
from apps.audit.services import record as audit
from core.files import load_pages
from core.identity import ssn
from core.identity.analyse import TYPES
from core.ocr import engine as ocr

from .models import DocumentAnalysis, DocumentComparison, SsnCheck
from .serializers import (AnalysisDetailSerializer, AnalysisListSerializer, CompareRequestSerializer,
                          ComparisonSerializer, SsnCheckSerializer, SsnRequestSerializer)
from .services import FileRejected, analyse_typed_mrz, analyse_upload, compare, purge_expired, visible_to

# Identity documents: analysts and reviewers do the work; administrators oversee it.
IdentityRoles = HasRole(Role.ADMINISTRATOR, Role.ANALYST, Role.REVIEWER)
AUTHORISATION_REQUIRED = "Confirm that you're authorised to process this document before analysing it."


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class MetaView(APIView):
    permission_classes = [IdentityRoles]

    @extend_schema(responses={200: dict})
    def get(self, request):
        available, engine = ocr.status()
        return Response({"types": [{"key": k, "label": v} for k, v in TYPES.items()],
                         "retention_days": settings.DOCUMENT_RETENTION_DAYS,
                         "ocr": {"available": available, "engine": engine}})


class AnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IdentityRoles]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "upload"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        purge_expired()  # retention is enforced on every request, even without a scheduled job

    def get_throttles(self):
        return super().get_throttles() if self.action == "create" else []

    def get_queryset(self):
        qs = visible_to(DocumentAnalysis.objects.select_related("created_by", "upload"), self.request.user)
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("type"):
            qs = qs.filter(detected_type=params["type"])
        if params.get("active") == "1":
            qs = qs.filter(purged_at__isnull=True)
        return qs

    def get_serializer_class(self):
        return AnalysisListSerializer if self.action == "list" else AnalysisDetailSerializer

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {
        "file": {"type": "string", "format": "binary"}, "mrz_text": {"type": "string"},
        "document_type": {"type": "string"}, "authorised": {"type": "boolean"}}}},
        responses={201: AnalysisDetailSerializer})
    def create(self, request):
        if not _truthy(request.data.get("authorised")):
            return Response({"detail": AUTHORISATION_REQUIRED}, status=status.HTTP_400_BAD_REQUEST)
        requested = str(request.data.get("document_type") or "auto")
        if requested not in TYPES:
            return Response({"detail": "Choose a supported document type."}, status=status.HTTP_400_BAD_REQUEST)

        upload = request.FILES.get("file")
        mrz_text = str(request.data.get("mrz_text") or "").strip()
        if upload is None and not mrz_text:
            return Response({"detail": "Upload a file or enter the machine-readable zone."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if upload is not None:
                analysis = analyse_upload(user=request.user, name=upload.name, data=upload.read(10 * 1024 * 1024 + 1),
                                          requested_type=requested)
            else:
                if len(mrz_text) > 200:
                    return Response({"detail": "That's too long for an MRZ (at most 3 lines of 44 characters)."},
                                    status=status.HTTP_400_BAD_REQUEST)
                analysis = analyse_typed_mrz(user=request.user, text=mrz_text, requested_type=requested)
        except FileRejected as rejected:
            return Response({"detail": str(rejected)}, status=status.HTTP_400_BAD_REQUEST)

        audit(request, "document.analysed", analysis, {
            "reference": analysis.reference, "source": analysis.source, "requested_type": requested,
            "detected_type": analysis.detected_type, "status": analysis.status, "authorised_confirmed": True})
        return Response(AnalysisDetailSerializer(analysis).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: AnalysisDetailSerializer})
    @action(detail=True, methods=["post"], url_path="delete-data")
    def delete_data(self, request, pk=None):
        """Delete this record's personal data and image now, ahead of the retention date."""
        analysis = self.get_object()
        if analysis.created_by != request.user and request.user.role != Role.ADMINISTRATOR:
            return Response({"detail": "Only the person who uploaded it, or an administrator, can delete it."},
                            status=status.HTTP_403_FORBIDDEN)
        if not analysis.purged:
            analysis.purge("deleted on request")
            audit(request, "document.data_deleted", analysis, {"reference": analysis.reference, "reason": "on request"})
        return Response(AnalysisDetailSerializer(analysis).data)

    @action(detail=True, methods=["get"])
    def image(self, request, pk=None):
        analysis = self.get_object()
        upload = analysis.upload
        if analysis.purged or upload is None or not upload.file_available:
            return Response({"detail": "The image is no longer stored."}, status=status.HTTP_404_NOT_FOUND)
        try:
            number = int(request.query_params.get("page", "1"))
        except ValueError:
            number = 1
        with upload.file.open("rb") as f:
            loaded = load_pages(upload.kind, f.read())
        page = next((p for p in loaded.pages if p.number == number), None)
        if page is None:
            return Response({"detail": "That page wasn't analysed."}, status=status.HTTP_404_NOT_FOUND)
        image = page.image
        image.thumbnail((1600, 1600))
        out = io.BytesIO()
        image.save(out, format="PNG")
        response = HttpResponse(out.getvalue(), content_type="image/png")
        response["Cache-Control"] = "no-store"  # identity images are never cached by the browser
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ComparisonViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IdentityRoles]
    serializer_class = ComparisonSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        purge_expired()

    def get_queryset(self):
        return visible_to(DocumentComparison.objects.prefetch_related("analyses"), self.request.user)

    @extend_schema(request=CompareRequestSerializer, responses={201: ComparisonSerializer})
    def create(self, request):
        body = CompareRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(body.validated_data["analysis_ids"]))
        analyses = list(visible_to(DocumentAnalysis.objects.filter(pk__in=ids, purged_at__isnull=True), request.user))
        if len(analyses) != len(ids) or len(ids) < 2:
            return Response({"detail": "Choose 2 to 4 different documents that you can view and that haven't been deleted."},
                            status=status.HTTP_400_BAD_REQUEST)
        analyses.sort(key=lambda a: ids.index(a.pk))
        record = compare(user=request.user, analyses=analyses)
        audit(request, "document.compared", record, {"reference": record.reference, "documents": len(analyses),
                                                     "status": record.status})
        return Response(ComparisonSerializer(record).data, status=status.HTTP_201_CREATED)


class SsnViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IdentityRoles]
    serializer_class = SsnCheckSerializer

    def get_queryset(self):
        return visible_to(SsnCheck.objects.all(), self.request.user)

    @extend_schema(request=SsnRequestSerializer, responses={201: dict})
    def create(self, request):
        body = SsnRequestSerializer(data=request.data)
        if not body.is_valid():
            return Response({"detail": "Enter a 9-digit number."}, status=status.HTTP_400_BAD_REQUEST)
        result = ssn.check(body.validated_data["number"])
        data = result.as_dict()
        record = SsnCheck.objects.create(created_by=request.user, masked=result.masked, format_valid=result.format_valid,
                                         status=result.status, checks=data["checks"])
        audit(request, "ssn.checked", record, {"status": result.status})  # no digits, not even masked
        return Response({**data, "id": record.pk, "created_at": record.created_at}, status=status.HTTP_201_CREATED)
