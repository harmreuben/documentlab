from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.system.views import StatusView, frontend

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/audit/", include("apps.audit.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/generator/", include("apps.barcode_generator.urls")),
    path("api/analyzer/", include("apps.barcode_decoder.urls")),
    path("api/documents/", include("apps.document_analysis.urls")),
    path("api/test-lab/", include("apps.test_lab.urls")),
    path("api/reviews/", include("apps.reviews.urls")),
    path("api/rules/", include("apps.rules.urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/system/status/", StatusView.as_view(), name="system-status"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # Production: every other address is a page of the React app (development uses Vite instead).
    re_path(r"^(?!api/|admin/|static/).*$", frontend, name="frontend"),
]
