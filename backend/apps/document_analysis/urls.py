from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalysisViewSet,
    ComparisonViewSet,
    MetaView,
    SsnViewSet,
    VerificationViewSet,
)

router = DefaultRouter()
router.register("analyses", AnalysisViewSet, basename="document-analysis")
router.register("comparisons", ComparisonViewSet, basename="document-comparison")
router.register("ssn-checks", SsnViewSet, basename="ssn-check")
router.register("ssn-verifications", VerificationViewSet, basename="ssn-verification")

urlpatterns = [
    path("meta/", MetaView.as_view(), name="documents-meta"),
    path("", include(router.urls)),
]
