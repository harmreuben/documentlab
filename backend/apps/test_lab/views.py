from django.db.models import Count, Q
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import HasRole, RoleAwareDefault
from apps.audit.services import record as audit
from core.files import FileRejected
from core.testlab import builtin, expect, runner

from .models import CaseResult, Fixture, TestRun
from .serializers import (
    AdoptSerializer,
    FixtureSerializer,
    FixtureWriteSerializer,
    RunDetailSerializer,
    RunListSerializer,
    RunRequestSerializer,
)
from .services import (
    RunInProgress,
    export_csv,
    export_json,
    export_junit,
    load_builtins,
    mark_stale_runs,
    save_file,
    screen_input,
    start_run,
    versions,
)

# Who may change the fixture library, and who may start runs. Everyone signed in can view results.
FixtureEditors = HasRole(Role.ADMINISTRATOR, Role.DEVELOPER)
RunStarters = HasRole(Role.ADMINISTRATOR, Role.DEVELOPER, Role.ANALYST, Role.REVIEWER)
CONTENT_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "pdf": "application/pdf"}


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class MetaView(APIView):
    permission_classes = [RoleAwareDefault]

    @extend_schema(responses={200: dict})
    def get(self, request):
        tags = sorted({t for tags in Fixture.objects.values_list("tags", flat=True) for t in (tags or [])})
        role = request.user.role
        return Response({
            "modules": [{"key": k, "label": v} for k, v in expect.MODULES.items()],
            "tags": tags,
            "builtin_count": len(builtin.BUILTINS),
            "builtin_loaded": Fixture.objects.filter(builtin_key__isnull=False).count(),
            "fixtures_active": Fixture.objects.filter(active=True).count(),
            "versions": versions(),
            "can_edit_fixtures": role in (Role.ADMINISTRATOR, Role.DEVELOPER),
            "can_add_document_images": role == Role.ADMINISTRATOR,
            "can_run": role in (Role.ADMINISTRATOR, Role.DEVELOPER, Role.ANALYST, Role.REVIEWER),
        })


class FixtureViewSet(viewsets.ModelViewSet):
    serializer_class = FixtureSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Fixture.objects.select_related("created_by")
        params = self.request.query_params
        if params.get("module"):
            qs = qs.filter(module=params["module"])
        if params.get("active") in ("0", "1"):
            qs = qs.filter(active=params["active"] == "1")
        if params.get("search"):
            qs = qs.filter(name__icontains=params["search"].strip())
        return qs

    def get_permissions(self):
        if self.action in ("list", "retrieve", "file"):
            return [RoleAwareDefault()]
        return [FixtureEditors()]

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {
        "name": {"type": "string"}, "module": {"type": "string"}, "expected": {"type": "string"},
        "file": {"type": "string", "format": "binary"}, "mrz_text": {"type": "string"},
        "synthetic": {"type": "boolean"}}}}, responses={201: FixtureSerializer})
    def create(self, request):
        if not _truthy(request.data.get("synthetic")):
            return Response({"detail": "Confirm that this fixture contains only synthetic (invented) data."},
                            status=status.HTTP_400_BAD_REQUEST)
        form = FixtureWriteSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        upload, mrz_text = request.FILES.get("file"), str(request.data.get("mrz_text", "")).strip()
        if bool(upload) == bool(mrz_text):
            return Response({"detail": "Give either a file or a typed MRZ, not both."}
                            if upload else {"detail": "Add a file, or type an MRZ for a Document Analysis fixture."},
                            status=status.HTTP_400_BAD_REQUEST)
        if mrz_text and data["module"] != "documents":
            return Response({"detail": "Typed MRZs are Document Analysis fixtures."}, status=status.HTTP_400_BAD_REQUEST)
        if upload and data["module"] == "documents" and request.user.role != Role.ADMINISTRATOR:
            return Response({"detail": "Only administrators can add document images as fixtures. "
                                       "Use a typed specimen MRZ instead."}, status=status.HTTP_403_FORBIDDEN)
        file_bytes = upload.read(10 * 1024 * 1024 + 1) if upload else None
        item = runner.FixtureInput(data["module"], upload.name if upload else "", file_bytes, mrz_text[:500], data["options"])
        try:
            screen_input(item)
        except FileRejected as rejected:
            audit(request, "testlab.fixture_refused", None, {"module": data["module"], "reason": str(rejected)[:120]})
            return Response({"detail": str(rejected)}, status=status.HTTP_400_BAD_REQUEST)

        fixture = Fixture(name=data["name"], description=data["description"], module=data["module"], tags=data["tags"],
                          options=data["options"], expected=data["expected"], active=data["active"],
                          created_by=request.user, input_type=Fixture.FILE if upload else Fixture.MRZ_TEXT,
                          mrz_text=mrz_text[:500])
        if upload:
            save_file(fixture, upload.name, file_bytes)
        fixture.save()
        audit(request, "testlab.fixture_created", fixture, {"name": fixture.name, "module": fixture.module})
        return Response(FixtureSerializer(fixture).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        fixture = self.get_object()
        if fixture.is_builtin:
            if set(request.data) - {"active"}:
                return Response({"detail": "Standard fixtures are defined in code so they can't drift. "
                                           "You can only switch them on or off."}, status=status.HTTP_400_BAD_REQUEST)
            fixture.active = _truthy(request.data.get("active"))
            fixture.save(update_fields=["active", "updated_at"])
        else:
            editable = ("name", "description", "tags", "options", "expected", "active")
            payload = {"name": fixture.name, "module": fixture.module, "expected": fixture.expected,
                       **{k: request.data[k] for k in editable if k in request.data}}
            form = FixtureWriteSerializer(data=payload)
            form.is_valid(raise_exception=True)
            for key in editable:
                if key in request.data:
                    setattr(fixture, key, form.validated_data[key])
            fixture.save()
        audit(request, "testlab.fixture_updated", fixture, {"name": fixture.name, "changed": sorted(request.data)})
        return Response(FixtureSerializer(fixture).data)

    def destroy(self, request, *args, **kwargs):
        fixture = self.get_object()
        if fixture.is_builtin:
            return Response({"detail": "Standard fixtures can't be deleted. Switch it off instead."},
                            status=status.HTTP_400_BAD_REQUEST)
        audit(request, "testlab.fixture_deleted", fixture, {"name": fixture.name})
        if fixture.file:
            fixture.file.delete(save=False)
        fixture.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        fixture = self.get_object()
        data = fixture.read_bytes() if fixture.file else None
        if data is None:
            return Response({"detail": "This fixture has no file."}, status=status.HTTP_404_NOT_FOUND)
        response = HttpResponse(data, content_type=CONTENT_TYPES.get(fixture.file_kind, "application/octet-stream"))
        response["Content-Disposition"] = f'inline; filename="{fixture.original_name or "fixture"}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="load-builtin")
    def load_builtin(self, request):
        created, updated = load_builtins(request.user)
        audit(request, "testlab.builtin_loaded", None, {"created": created, "updated": updated})
        return Response({"created": created, "updated": updated})

    @extend_schema(request=AdoptSerializer, responses={200: FixtureSerializer})
    @action(detail=True, methods=["post"])
    def adopt(self, request, pk=None):
        """Make a reviewed result this fixture's expected result."""
        fixture = self.get_object()
        if fixture.is_builtin:
            return Response({"detail": "Standard fixtures' expected results are fixed in code."},
                            status=status.HTTP_400_BAD_REQUEST)
        form = AdoptSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        case = CaseResult.objects.filter(pk=form.validated_data["case_id"], fixture=fixture).first()
        if case is None or not case.actual:
            return Response({"detail": "That result doesn't belong to this fixture, or has no output to use."},
                            status=status.HTTP_400_BAD_REQUEST)
        fixture.expected = expect.validate(fixture.module, expect.from_actual(fixture.module, case.actual))
        fixture.save(update_fields=["expected", "updated_at"])
        audit(request, "testlab.expected_adopted", fixture, {"name": fixture.name, "run": case.run.reference})
        return Response(FixtureSerializer(fixture).data)


class RunViewSet(viewsets.ReadOnlyModelViewSet):
    def get_queryset(self):
        qs = TestRun.objects.select_related("created_by", "baseline").annotate(
            new_failures=Count("cases", filter=Q(cases__change=CaseResult.NEW_FAILURE)),
            fixed=Count("cases", filter=Q(cases__change=CaseResult.FIXED))
        ).order_by("-created_at", "-id")  # grouped queries ignore Meta.ordering, so it must be explicit
        if self.action == "retrieve":
            qs = qs.prefetch_related("cases")
        return qs

    def get_serializer_class(self):
        return RunDetailSerializer if self.action == "retrieve" else RunListSerializer

    def get_permissions(self):
        return [RunStarters()] if self.action == "create" else [RoleAwareDefault()]

    def list(self, request, *args, **kwargs):
        mark_stale_runs()
        return super().list(request, *args, **kwargs)

    @extend_schema(request=RunRequestSerializer, responses={201: RunDetailSerializer})
    def create(self, request):
        form = RunRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        scope = {k: v for k, v in form.validated_data.items() if k != "note" and v}
        try:
            run = start_run(request.user, scope, form.validated_data["note"])
        except RunInProgress as busy:
            return Response({"detail": str(busy)}, status=status.HTTP_409_CONFLICT)
        except ValueError as empty:
            return Response({"detail": str(empty)}, status=status.HTTP_400_BAD_REQUEST)
        audit(request, "testlab.run_started", run, {"reference": run.reference, "fixtures": run.total, "scope": scope})
        return Response(RunDetailSerializer(self.get_queryset().get(pk=run.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[OpenApiParameter("type", str, enum=["json", "csv", "junit"])])
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        run = self.get_object()
        kind = request.query_params.get("type", "json")
        builders = {"json": (export_json, "application/json", "json"), "csv": (export_csv, "text/csv; charset=utf-8", "csv"),
                    "junit": (export_junit, "application/xml", "xml")}
        if kind not in builders:
            return Response({"detail": "Choose json, csv or junit."}, status=status.HTTP_400_BAD_REQUEST)
        build, content_type, extension = builders[kind]
        response = HttpResponse(build(run), content_type=content_type)
        suffix = "-junit" if kind == "junit" else ""
        response["Content-Disposition"] = f'attachment; filename="{run.reference}{suffix}.{extension}"'
        return response
