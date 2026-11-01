import io

from django.db.models import Prefetch
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.audit.services import record as audit
from apps.barcode_generator.models import GeneratedBarcode
from core.files import FileRejected, load_pages

from .models import BarcodeAnalysis, DecodedBarcode
from .serializers import AnalysisDetailSerializer, AnalysisListSerializer
from .services import export_csv, export_json, run_analysis

PREVIEW_MAX_SIDE = 1600


class FromGeneratedSerializer(serializers.Serializer):
    test_reference = serializers.CharField(max_length=32)
    expected = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class AnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    """Upload a PNG, JPEG or PDF; every barcode in it is decoded, checked and stored as one analysis."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "upload"

    def get_queryset(self):
        qs = (BarcodeAnalysis.objects.select_related("created_by", "upload", "source_generated")
              .prefetch_related(Prefetch("barcodes", queryset=DecodedBarcode.objects.select_related("matched_generated"))))
        if self.request.user.role != Role.ADMINISTRATOR:
            qs = qs.filter(created_by=self.request.user)
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("search"):
            term = params["search"].strip()
            qs = qs.filter(reference__icontains=term) | qs.filter(upload__original_name__icontains=term)
        return qs

    def get_serializer_class(self):
        return AnalysisListSerializer if self.action == "list" else AnalysisDetailSerializer

    def get_throttles(self):
        # Only uploads are rate-limited; browsing results is not.
        return super().get_throttles() if self.action in ("create", "from_generated") else []

    def _respond(self, request, analysis):
        audit(request, "barcode.analysed", analysis, {
            "reference": analysis.reference, "status": analysis.status, "kind": analysis.upload.kind,
            "size_bytes": analysis.upload.size_bytes, "barcodes": analysis.barcodes.count(),
            "sensitive": analysis.sensitive})
        return Response(AnalysisDetailSerializer(self.get_queryset().get(pk=analysis.pk)).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {
        "file": {"type": "string", "format": "binary"}, "expected": {"type": "string"}}}},
        responses={201: AnalysisDetailSerializer})
    def create(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Choose a PNG, JPEG or PDF file to analyse."}, status=status.HTTP_400_BAD_REQUEST)
        data = upload.read(10 * 1024 * 1024 + 1)  # read one byte past the limit to detect oversize files
        try:
            analysis = run_analysis(user=request.user, name=upload.name, data=data,
                                    expected=str(request.data.get("expected", ""))[:2000])
        except FileRejected as rejected:
            return Response({"detail": str(rejected)}, status=status.HTTP_400_BAD_REQUEST)
        return self._respond(request, analysis)

    @extend_schema(request=FromGeneratedSerializer, responses={201: AnalysisDetailSerializer})
    @action(detail=False, methods=["post"], url_path="from-generated")
    def from_generated(self, request):
        """Analyse a barcode made in the Generator, using its saved PNG."""
        body = FromGeneratedSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        generated = GeneratedBarcode.objects.filter(test_reference=body.validated_data["test_reference"].strip().upper())
        if request.user.role != Role.ADMINISTRATOR:
            generated = generated.filter(created_by=request.user)
        generated = generated.first()
        if generated is None:
            return Response({"detail": "No generated barcode with that reference is available to you."},
                            status=status.HTTP_404_NOT_FOUND)
        with generated.png.open("rb") as f:
            data = f.read()
        expected = body.validated_data["expected"] or generated.expected_decode
        analysis = run_analysis(user=request.user, name=f"{generated.test_reference}.png", data=data,
                                expected=expected, source_generated=generated)
        return self._respond(request, analysis)

    @extend_schema(parameters=[OpenApiParameter("page", int)], responses={200: bytes})
    @action(detail=True, methods=["get"])
    def image(self, request, pk=None):
        """A page of the uploaded file as PNG, re-encoded (so photo metadata such as location is dropped)."""
        analysis = self.get_object()
        upload = analysis.upload
        if not upload.file_available:
            return Response({"detail": upload.file_removed_reason or "The file is no longer stored."},
                            status=status.HTTP_404_NOT_FOUND)
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
        image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        response = HttpResponse(out.getvalue(), content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(parameters=[OpenApiParameter("type", str, enum=["json", "csv"])], responses={200: bytes})
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        analysis = self.get_object()
        kind = request.query_params.get("type", "json")
        if kind == "csv":
            content, ctype, ext = export_csv(analysis).encode("utf-8-sig"), "text/csv", "csv"
        elif kind == "json":
            content, ctype, ext = export_json(analysis, AnalysisDetailSerializer(analysis).data).encode(), "application/json", "json"
        else:
            return Response({"detail": "Choose json or csv."}, status=status.HTTP_400_BAD_REQUEST)
        response = HttpResponse(content, content_type=ctype)
        response["Content-Disposition"] = f'attachment; filename="{analysis.reference}.{ext}"'
        return response
