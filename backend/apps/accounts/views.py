from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record

from .models import User
from .permissions import IsAdministrator
from .serializers import LoginSerializer, MeSerializer, UserAdminSerializer


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the csrftoken cookie. The React app calls this once before logging in."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"  # 5 attempts per minute per client

    @extend_schema(request=LoginSerializer, responses={200: MeSerializer})
    def post(self, request):
        # DRF only checks CSRF for users who are already logged in, so the
        # login form would otherwise be unprotected. Enforce it explicitly.
        SessionAuthentication().enforce_csrf(request)
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(request, **data.validated_data)
        if user is None:
            # Same message whether the username or the password was wrong.
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]  # read-only users must also be able to log out

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses={200: MeSerializer})
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    """User management - administrators only. Users are deactivated, never deleted, to keep the audit trail."""

    queryset = User.objects.order_by("username")
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdministrator]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        user = serializer.save()
        record(self.request, "user.created", user, {"role": user.role})

    def perform_update(self, serializer):
        before = {"role": serializer.instance.role, "is_active": serializer.instance.is_active}
        user = serializer.save()
        changes = {k: v for k, v in serializer.validated_data.items() if k != "password"}
        if "password" in serializer.validated_data:
            changes["password"] = "changed"
        record(self.request, "user.updated", user, {"before": before, "changes": changes})
