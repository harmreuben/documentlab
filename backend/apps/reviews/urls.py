from django.urls import path

from .views import DecisionView, QueueView

urlpatterns = [
    path("", QueueView.as_view(), name="review-queue"),
    path("<str:kind>/<int:pk>/", DecisionView.as_view(), name="review-decide"),
]
