from rest_framework.routers import DefaultRouter

from .views import AnalysisViewSet

router = DefaultRouter()
router.register("analyses", AnalysisViewSet, basename="barcode-analysis")

urlpatterns = router.urls
