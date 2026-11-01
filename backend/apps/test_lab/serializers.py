import json

from rest_framework import serializers

from core.identity.analyse import TYPES
from core.testlab import expect

from .models import CaseResult, Fixture, TestRun


def _json_field(value, what: str):
    """Multipart forms send JSON as text; accept either."""
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError(f"{what} isn't valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno}).")
    return value


class RawField(serializers.Field):
    """Accepts JSON as an object or as text, so `validate` can give a precise message when the text is broken."""

    def to_internal_value(self, data):
        return data

    def to_representation(self, value):
        return value


class FixtureSerializer(serializers.ModelSerializer):
    module_label = serializers.SerializerMethodField()
    is_builtin = serializers.BooleanField(read_only=True)
    created_by = serializers.SerializerMethodField()
    last_result = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()

    class Meta:
        model = Fixture
        fields = ["id", "name", "description", "module", "module_label", "tags", "is_builtin", "builtin_key", "input_type",
                  "original_name", "file_kind", "size_bytes", "mrz_text", "options", "expected", "active",
                  "created_by", "created_at", "updated_at", "last_result", "links"]

    def get_module_label(self, obj) -> str:
        return expect.MODULES.get(obj.module, obj.module)

    def get_created_by(self, obj) -> str | None:
        return obj.created_by.get_username() if obj.created_by else None

    def get_last_result(self, obj) -> dict | None:
        case = obj.results.select_related("run").order_by("-run__created_at", "-id").first()
        if case is None:
            return None
        return {"outcome": case.outcome, "run_id": case.run_id, "run_reference": case.run.reference,
                "at": case.run.created_at}

    def get_links(self, obj) -> dict:
        return {"file": f"/api/test-lab/fixtures/{obj.pk}/file/" if obj.file else None}


class FixtureWriteSerializer(serializers.Serializer):
    """Validates the editable parts of a fixture. The input itself (file or MRZ) is checked in the view."""

    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    module = serializers.ChoiceField(choices=list(expect.MODULES))
    tags = RawField(required=False, default=list)
    options = RawField(required=False, default=dict)
    expected = RawField()
    active = serializers.BooleanField(required=False, default=True)

    def validate_tags(self, value):
        value = _json_field(value, "Tags") if isinstance(value, str) and value.strip().startswith("[") else value
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            raise serializers.ValidationError("Give tags as a list or comma-separated text.")
        tags = sorted({str(t).strip().lower()[:24] for t in value if str(t).strip()})
        if len(tags) > 10:
            raise serializers.ValidationError("Use at most 10 tags.")
        return tags

    def validate(self, attrs):
        module = attrs.get("module") or getattr(self.instance, "module", None)
        options = _json_field(attrs.get("options", {}), "Options") or {}
        if not isinstance(options, dict):
            raise serializers.ValidationError({"options": "Give options as an object."})
        allowed = {"analyzer": {"expected_value"}, "documents": {"document_type"}}[module]
        if set(options) - allowed:
            raise serializers.ValidationError({"options": f"Only {', '.join(sorted(allowed))} can be set for this module."})
        if "expected_value" in options:
            options["expected_value"] = str(options["expected_value"])[:2000]
        if "document_type" in options and options["document_type"] not in TYPES:
            raise serializers.ValidationError({"options": f"document_type must be one of {', '.join(TYPES)}."})
        attrs["options"] = options
        if "expected" in attrs:
            try:
                attrs["expected"] = expect.validate(module, _json_field(attrs["expected"], "Expected result"))
            except expect.InvalidExpectation as exc:
                raise serializers.ValidationError({"expected": str(exc)})
        return attrs


class CaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseResult
        fields = ["id", "fixture", "position", "fixture_name", "module", "outcome", "change", "previous_outcome",
                  "expected", "actual", "comparisons", "error", "duration_ms"]


class RunListSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    done = serializers.IntegerField(read_only=True)
    baseline = serializers.SerializerMethodField()
    new_failures = serializers.IntegerField(read_only=True, default=0)
    fixed = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TestRun
        fields = ["id", "reference", "status", "scope", "note", "total", "done", "passed", "failed", "errors",
                  "new_failures", "fixed", "versions", "baseline", "created_by", "created_at", "finished_at", "duration_ms"]

    def get_created_by(self, obj) -> str | None:
        return obj.created_by.get_username() if obj.created_by else None

    def get_baseline(self, obj) -> dict | None:
        return {"id": obj.baseline_id, "reference": obj.baseline.reference} if obj.baseline_id else None


class RunDetailSerializer(RunListSerializer):
    cases = CaseSerializer(many=True, read_only=True)
    links = serializers.SerializerMethodField()

    class Meta(RunListSerializer.Meta):
        fields = RunListSerializer.Meta.fields + ["cases", "links"]

    def get_links(self, obj) -> dict:
        base = f"/api/test-lab/runs/{obj.pk}/export/"
        return {"json": base + "?type=json", "csv": base + "?type=csv", "junit": base + "?type=junit", "pdf": base + "?type=pdf"}


class RunRequestSerializer(serializers.Serializer):
    module = serializers.ChoiceField(choices=list(expect.MODULES), required=False, allow_blank=True)
    tag = serializers.CharField(max_length=24, required=False, allow_blank=True)
    fixture_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=500)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class AdoptSerializer(serializers.Serializer):
    case_id = serializers.IntegerField(min_value=1)
