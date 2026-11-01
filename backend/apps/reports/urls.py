from django.urls import path

from .views import SummaryView

urlpatterns = [path("summary/", SummaryView.as_view(), name="report-summary")]
