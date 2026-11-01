from rest_framework import serializers

from core.identity.analyse import AUTHENTICITY, TYPES

from .models import DocumentAnalysis, DocumentComparison, SsnCheck


def masked_number(fields: dict) -> str:
    value = (fields.get("document_number") or {}).get("value", "")
    return ("•" * max(0, len(value) - 3) + value[-3:]) if value else ""


class AnalysisListSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    document_label = serializers.SerializerMethodField()
    holder = serializers.SerializerMethodField()
    number = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAnalysis
        fields = ["id", "reference", "created_at", "created_by", "source", "detected_type", "document_label",
                  "status", "holder", "number", "expires_at", "purged_at"]

    def get_document_label(self, obj):
        return TYPES.get(obj.detected_type, "Unknown document")

    def get_holder(self, obj):
        # Lists show only the surname initial; full names are on the detail page.
        surname = (obj.fields.get("surname") or {}).get("value", "")
        return f"{surname[0]}." if surname else ""

    def get_number(self, obj):
        return masked_number(obj.fields)


class AnalysisDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    document_label = serializers.SerializerMethodField()
    upload = serializers.SerializerMethodField()
    authenticity = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAnalysis
        fields = ["id", "reference", "created_at", "created_by", "source", "requested_type", "detected_type",
                  "document_label", "status", "summary", "next_action", "checks", "fields", "mrz", "licence", "ocr",
                  "pages", "warnings", "ocr_engine", "duration_ms", "authenticity", "upload", "expires_at",
                  "purged_at", "purge_reason", "links"]

    def get_document_label(self, obj):
        return TYPES.get(obj.detected_type, "Unknown document")

    def get_authenticity(self, obj):
        return AUTHENTICITY

    def get_upload(self, obj):
        u = obj.upload
        if u is None:
            return None
        return {"original_name": u.original_name, "kind": u.kind, "size_bytes": u.size_bytes, "sha256": u.sha256,
                "page_count": u.page_count, "file_available": u.file_available}

    def get_links(self, obj):
        if obj.upload and obj.upload.file_available and not obj.purged:
            return {"pages": [f"/api/documents/analyses/{obj.pk}/image/?page={p['page']}" for p in obj.pages]}
        return {"pages": []}


class ComparisonSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    documents = serializers.SerializerMethodField()

    class Meta:
        model = DocumentComparison
        fields = ["id", "reference", "created_at", "created_by", "status", "summary", "rows", "documents",
                  "expires_at", "purged_at"]

    def get_documents(self, obj):
        return [{"id": a.pk, "reference": a.reference, "document_label": TYPES.get(a.detected_type, "Unknown")}
                for a in obj.analyses.all()]


class CompareRequestSerializer(serializers.Serializer):
    analysis_ids = serializers.ListField(child=serializers.IntegerField(), min_length=2, max_length=4)


class SsnRequestSerializer(serializers.Serializer):
    # The value is never echoed back in errors or responses.
    number = serializers.CharField(max_length=20, trim_whitespace=True,
                                   error_messages={"max_length": "Enter at most 11 characters."})


class SsnCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = SsnCheck
        fields = ["id", "created_at", "masked", "format_valid", "status", "checks"]
