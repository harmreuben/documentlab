from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FixtureViewSet, MetaView, RunViewSet

router = DefaultRouter()
router.register("fixtures", FixtureViewSet, basename="test-fixture")
router.register("runs", RunViewSet, basename="test-run")

urlpatterns = [
    path("meta/", MetaView.as_view(), name="test-lab-meta"),
    path("", include(router.urls)),
]
