from django.urls import path

from .views import RulesView

urlpatterns = [path("", RulesView.as_view(), name="rules")]
