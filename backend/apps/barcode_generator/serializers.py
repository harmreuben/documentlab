from rest_framework import serializers

from core.barcodes import SYMBOLOGIES
from core.barcodes.schemas import SCHEMAS, TEXT_SCHEMA

from .models import GeneratedBarcode, GenerationBatch


class BarcodeRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=sorted(SYMBOLOGIES))
    schema = serializers.ChoiceField(choices=sorted(SCHEMAS), default=TEXT_SCHEMA)
    payload = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False, max_length=5000)
    fields = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=500),
                                   required=False, default=dict)
    options = serializers.DictField(required=False, default=dict)
    label = serializers.CharField(required=False, allow_blank=True, max_length=80, default="")


class GeneratedBarcodeSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None, read_only=True)
    batch = serializers.PrimaryKeyRelatedField(read_only=True)
    downloads = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedBarcode
        fields = [
            "id", "test_reference", "created_at", "created_by", "batch", "batch_row",
            "format", "schema_id", "label", "input_payload", "input_fields", "expected_decode", "check_digit",
            "options", "render_details", "warnings", "png_sha256", "width_px", "height_px",
            "verification_status", "decoded_text", "decoded_format", "verification_detail",
            "download_count", "last_downloaded_at", "downloads",
        ]
        read_only_fields = fields

    def get_downloads(self, obj):
        base = f"/api/generator/barcodes/{obj.pk}/download/"
        return {kind: f"{base}?type={kind}" for kind in ("png", "svg", "pdf")}


class GenerationBatchSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None, read_only=True)
    downloads = serializers.SerializerMethodField()

    class Meta:
        model = GenerationBatch
        fields = ["id", "created_at", "created_by", "source_name", "total_rows", "succeeded", "failed",
                  "options", "report", "downloads"]
        read_only_fields = fields

    def get_downloads(self, obj):
        base = f"/api/generator/batches/{obj.pk}/download/"
        return {"zip": f"{base}?type=zip", "pdf": f"{base}?type=pdf", "csv": f"{base}?type=csv"}
