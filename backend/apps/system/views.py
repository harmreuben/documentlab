"""The React app's entry page, and the administrators' security status."""
from django.conf import settings
from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdministrator

from .status import security_status


def frontend(request, path=""):
    """Every page address (/documents/7, /rules, ...) returns index.html; React shows the right page."""
    index = settings.FRONTEND_DIST / "index.html"
    if not settings.SERVE_FRONTEND or not index.exists():
        raise Http404("The website isn't built. Run 'npm run build' in the frontend folder.")
    response = FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"  # always pick up a new build; the hashed assets are cached
    return response


class StatusView(APIView):
    permission_classes = [IsAdministrator]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(security_status())
