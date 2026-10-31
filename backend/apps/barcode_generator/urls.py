from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BarcodeViewSet, BatchViewSet, CheckView, FormatsView, SampleView

router = DefaultRouter()
router.register("barcodes", BarcodeViewSet, basename="generated-barcode")
router.register("batches", BatchViewSet, basename="generation-batch")

urlpatterns = [
    path("formats/", FormatsView.as_view(), name="generator-formats"),
    path("check/", CheckView.as_view(), name="generator-check"),
    path("sample/", SampleView.as_view(), name="generator-sample"),
    path("", include(router.urls)),
]
