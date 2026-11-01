from rest_framework import serializers

from .models import BarcodeAnalysis, DecodedBarcode


class DecodedBarcodeSerializer(serializers.ModelSerializer):
    matched_generated = serializers.SerializerMethodField()

    class Meta:
        model = DecodedBarcode
        exclude = ["analysis"]

    def get_matched_generated(self, obj):
        g = obj.matched_generated
        if g is None:
            return None
        return {"id": g.pk, "test_reference": g.test_reference, "format": g.format,
                "created_at": g.created_at, "verification_status": g.verification_status}


class UploadSummarySerializer(serializers.Serializer):
    original_name = serializers.CharField()
    kind = serializers.CharField()
    size_bytes = serializers.IntegerField()
    sha256 = serializers.CharField()
    page_count = serializers.IntegerField()
    file_available = serializers.BooleanField()
    file_removed_reason = serializers.CharField()


class AnalysisListSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    file_name = serializers.CharField(source="upload.original_name")
    file_kind = serializers.CharField(source="upload.kind")
    barcode_count = serializers.IntegerField(source="barcodes.count")
    formats = serializers.SerializerMethodField()

    class Meta:
        model = BarcodeAnalysis
        fields = ["id", "reference", "created_at", "created_by", "file_name", "file_kind", "status",
                  "summary", "barcode_count", "formats", "sensitive"]

    def get_formats(self, obj):
        return sorted({b.format_name for b in obj.barcodes.all()})


class AnalysisDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)
    upload = UploadSummarySerializer()
    barcodes = DecodedBarcodeSerializer(many=True)
    source_generated = serializers.CharField(source="source_generated.test_reference", default=None)
    links = serializers.SerializerMethodField()

    class Meta:
        model = BarcodeAnalysis
        fields = ["id", "reference", "created_at", "created_by", "upload", "source_generated", "expected_value",
                  "status", "summary", "next_action", "checks", "pages", "warnings", "sensitive",
                  "duration_ms", "decoder", "barcodes", "links"]

    def get_links(self, obj):
        base = f"/api/analyzer/analyses/{obj.pk}"
        links = {"json": f"{base}/export/?type=json", "csv": f"{base}/export/?type=csv"}
        if obj.upload.file_available:
            links["pages"] = [f"{base}/image/?page={p['page']}" for p in obj.pages]
        return links
