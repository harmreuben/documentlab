import base64
import json

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.audit.services import record as audit
from core.barcodes import SYMBOLOGIES, generate
from core.barcodes.options import option_specs
from core.barcodes.samples import sample
from core.barcodes.schemas import SCHEMAS, TEXT_SCHEMA

from .models import GeneratedBarcode, GenerationBatch
from .serializers import BarcodeRequestSerializer, GeneratedBarcodeSerializer, GenerationBatchSerializer
from .services import BatchProblem, GenerationRefused, batch_report_csv, batch_zip, create_barcode, labels_pdf, run_batch


def _visible(queryset, user):
    """Administrators see everyone's barcodes; everyone else sees their own."""
    return queryset if user.role == Role.ADMINISTRATOR else queryset.filter(created_by=user)


class FormatsView(APIView):
    """Everything the studio needs to draw its form: formats, option controls and schemas."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({
            "formats": [{
                "key": s.key, "name": s.name, "family": s.family, "summary": s.summary,
                "max_length": s.max_length, "structured": s.structured,
                "digits": list(s.data_lengths) if s.data_lengths else None, "notes": s.notes,
                "options": [o.as_dict() for o in option_specs(s.family)],
            } for s in SYMBOLOGIES.values()],
            "schemas": [schema.as_dict() for schema in SCHEMAS.values()],
            "default_schema": TEXT_SCHEMA,
        })


class CheckView(APIView):
    """Validate and preview without saving anything. Used for live feedback while typing."""

    throttle_scope = "preview"

    @extend_schema(request=BarcodeRequestSerializer, responses={200: dict})
    def post(self, request):
        data = BarcodeRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        result = generate(v["format"], v.get("payload"), v["options"], v["schema"], v["fields"])
        body = result.check.as_dict()
        body["preview"] = None
        body["verification"] = None
        if result.ok:
            body["preview"] = {
                "svg_data_url": "data:image/svg+xml;base64," + base64.b64encode(result.output.svg.encode()).decode(),
                "width": result.output.width, "height": result.output.height, "details": result.output.details,
            }
            body["verification"] = result.verification.as_dict()
        return Response(body)


class SampleView(APIView):
    @extend_schema(parameters=[OpenApiParameter("format", str), OpenApiParameter("schema", str)], responses={200: dict})
    def get(self, request):
        format_key = request.query_params.get("format", "qr")
        schema_id = request.query_params.get("schema", TEXT_SCHEMA)
        if format_key not in SYMBOLOGIES or schema_id not in SCHEMAS:
            return Response({"detail": "Unknown format or schema."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(sample(format_key, schema_id))


def _file_response(content: bytes, content_type: str, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


class BarcodeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GeneratedBarcodeSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # API schema generation, no signed-in user
            return GeneratedBarcode.objects.none()
        qs = _visible(GeneratedBarcode.objects.select_related("created_by"), self.request.user)
        params = self.request.query_params
        if params.get("format"):
            qs = qs.filter(format=params["format"])
        if params.get("status"):
            qs = qs.filter(verification_status=params["status"])
        if params.get("batch"):
            qs = qs.filter(batch_id=params["batch"])
        if params.get("search"):
            qs = qs.filter(test_reference__icontains=params["search"].strip()) | qs.filter(label__icontains=params["search"].strip())
        return qs

    @extend_schema(request=BarcodeRequestSerializer, responses={201: GeneratedBarcodeSerializer})
    def create(self, request):
        data = BarcodeRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        try:
            barcode = create_barcode(user=request.user, format_key=v["format"], payload=v.get("payload"),
                                     options=v["options"], schema_id=v["schema"], fields=v["fields"], label=v["label"])
        except GenerationRefused as refused:
            if refused.result.blocked:
                audit(request, "barcode.refused", metadata={"format": v["format"], "reason": "identity layout"})
            return Response({"detail": refused.result.errors[0]["message"], **refused.result.as_dict()},
                            status=status.HTTP_400_BAD_REQUEST)
        audit(request, "barcode.generated", barcode,
              {"test_reference": barcode.test_reference, "format": barcode.format,
               "schema": barcode.schema_id, "verification": barcode.verification_status})
        return Response(GeneratedBarcodeSerializer(barcode).data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[OpenApiParameter("type", str, enum=["png", "svg", "pdf"])], responses={200: bytes})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        barcode = self.get_object()
        kind = request.query_params.get("type", "png")
        if kind == "png":
            with barcode.png.open("rb") as f:
                response = _file_response(f.read(), "image/png", f"{barcode.test_reference}.png")
        elif kind == "svg":
            with barcode.svg.open("rb") as f:
                response = _file_response(f.read(), "image/svg+xml", f"{barcode.test_reference}.svg")
        elif kind == "pdf":
            response = _file_response(labels_pdf([barcode]), "application/pdf", f"{barcode.test_reference}.pdf")
        else:
            return Response({"detail": "Choose png, svg or pdf."}, status=status.HTTP_400_BAD_REQUEST)
        GeneratedBarcode.objects.filter(pk=barcode.pk).update(download_count=barcode.download_count + 1,
                                                              last_downloaded_at=timezone.now())
        return response


class BatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GenerationBatchSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # API schema generation, no signed-in user
            return GenerationBatch.objects.none()
        return _visible(GenerationBatch.objects.select_related("created_by"), self.request.user)

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {
        "file": {"type": "string", "format": "binary"}, "options": {"type": "string"}}}},
        responses={201: GenerationBatchSerializer})
    def create(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Choose a CSV file to upload."}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith(".csv"):
            return Response({"detail": "Upload a .csv file."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            options = json.loads(request.data.get("options") or "{}")
            if not isinstance(options, dict):
                raise ValueError
        except ValueError:
            return Response({"detail": "Options must be a JSON object."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            batch = run_batch(user=request.user, filename=upload.name, raw=upload.read(), options=options)
        except BatchProblem as problem:
            return Response({"detail": problem.message}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, "barcode.batch_generated", batch,
              {"rows": batch.total_rows, "succeeded": batch.succeeded, "failed": batch.failed})
        return Response(GenerationBatchSerializer(batch).data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[OpenApiParameter("type", str, enum=["zip", "pdf", "csv"])], responses={200: bytes})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        batch = get_object_or_404(self.get_queryset(), pk=pk)
        kind = request.query_params.get("type", "zip")
        name = f"documentlab-batch-{batch.pk}"
        if kind == "zip":
            return _file_response(batch_zip(batch), "application/zip", f"{name}.zip")
        if kind == "pdf":
            return _file_response(labels_pdf(list(batch.barcodes.order_by("batch_row"))), "application/pdf", f"{name}.pdf")
        if kind == "csv":
            return _file_response(batch_report_csv(batch).encode("utf-8-sig"), "text/csv", f"{name}-report.csv")
        return Response({"detail": "Choose zip, pdf or csv."}, status=status.HTTP_400_BAD_REQUEST)
