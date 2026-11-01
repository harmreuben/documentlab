from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.reviews.services import review_info
from core.identity.analyse import AUTHENTICITY, TYPES
from core.verification.base import CONSENT_METHODS, PURPOSES

from .models import DocumentAnalysis, DocumentComparison, SsnCheck, SsnVerification


def masked_number(fields: dict) -> str:
    value = (fields.get("document_number") or {}).get("value", "")
    return ("•" * max(0, len(value) - 3) + value[-3:]) if value else ""


@extend_schema_serializer(component_name="DocumentAnalysisList")
class AnalysisListSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    document_label = serializers.SerializerMethodField()
    holder = serializers.SerializerMethodField()
    number = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAnalysis
        fields = ["id", "reference", "created_at", "created_by", "source", "detected_type", "document_label",
                  "status", "holder", "number", "expires_at", "purged_at", "review_state"]

    def get_document_label(self, obj) -> str:
        return TYPES.get(obj.detected_type, "Unknown document")

    def get_holder(self, obj) -> str:
        # Lists show only the surname initial; full names are on the detail page.
        surname = (obj.fields.get("surname") or {}).get("value", "")
        return f"{surname[0]}." if surname else ""

    def get_number(self, obj) -> str:
        return masked_number(obj.fields)


@extend_schema_serializer(component_name="DocumentAnalysisDetail")
class AnalysisDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    document_label = serializers.SerializerMethodField()
    upload = serializers.SerializerMethodField()
    authenticity = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAnalysis
        fields = ["id", "reference", "created_at", "created_by", "source", "requested_type", "detected_type",
                  "document_label", "status", "summary", "next_action", "checks", "fields", "mrz", "licence", "ocr",
                  "pages", "warnings", "ocr_engine", "duration_ms", "authenticity", "upload", "expires_at",
                  "purged_at", "purge_reason", "ruleset_version", "review", "links"]

    def get_review(self, obj) -> dict:
        return review_info(obj)

    def get_document_label(self, obj) -> str:
        return TYPES.get(obj.detected_type, "Unknown document")

    def get_authenticity(self, obj) -> dict:
        return AUTHENTICITY

    def get_upload(self, obj) -> dict | None:
        u = obj.upload
        if u is None:
            return None
        return {"original_name": u.original_name, "kind": u.kind, "size_bytes": u.size_bytes, "sha256": u.sha256,
                "page_count": u.page_count, "file_available": u.file_available}

    def get_links(self, obj) -> dict:
        report = f"/api/documents/analyses/{obj.pk}/report/"
        if obj.upload and obj.upload.file_available and not obj.purged:
            return {"pages": [f"/api/documents/analyses/{obj.pk}/image/?page={p['page']}" for p in obj.pages], "pdf": report}
        return {"pages": [], "pdf": report}


class ComparisonSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    documents = serializers.SerializerMethodField()

    class Meta:
        model = DocumentComparison
        fields = ["id", "reference", "created_at", "created_by", "status", "summary", "rows", "documents",
                  "expires_at", "purged_at"]

    def get_documents(self, obj) -> list[dict]:
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
        fields = ["id", "created_at", "masked", "format_valid", "status", "checks", "ruleset_version"]


class SsnVerificationRequestSerializer(serializers.Serializer):
    number = serializers.CharField(max_length=11)
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60)
    birth_date = serializers.DateField()
    consent_method = serializers.ChoiceField(choices=list(CONSENT_METHODS))
    consent_reference = serializers.CharField(max_length=80)
    consent_signed_on = serializers.DateField()
    purpose = serializers.ChoiceField(choices=list(PURPOSES))
    consent_confirmed = serializers.BooleanField()

    def validate_consent_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Confirm that the person signed a consent form for this check.")
        return value

    def validate(self, attrs):
        from datetime import date
        if attrs["consent_signed_on"] > date.today():
            raise serializers.ValidationError({"consent_signed_on": "The consent can't be signed in the future."})
        if attrs["birth_date"] >= date.today():
            raise serializers.ValidationError({"birth_date": "Enter a date in the past."})
        return attrs


class SsnVerificationSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    summary = serializers.SerializerMethodField()
    purpose_label = serializers.SerializerMethodField()

    class Meta:
        model = SsnVerification
        fields = ["id", "created_at", "created_by", "masked", "provider", "outcome", "status", "mismatched", "deceased",
                  "provider_reference", "consent_method", "consent_reference", "consent_signed_on", "purpose",
                  "purpose_label", "summary", "ruleset_version"]

    def get_summary(self, obj) -> str:
        from .verification import summary
        return summary(obj)

    def get_purpose_label(self, obj) -> str:
        return PURPOSES.get(obj.purpose, obj.purpose)
