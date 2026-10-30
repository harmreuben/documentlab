"""Role-based permissions used by every DocumentLab API view.

Rules:
- Nobody gets in without logging in.
- Read-only users may only read (GET, HEAD, OPTIONS).
- Views narrow access further with HasRole(...) or IsAdministrator.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


class RoleAwareDefault(BasePermission):
    """Default for all views: logged in, and read-only users cannot change anything."""

    message = "Your role does not allow this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if user.role == Role.READ_ONLY and request.method not in SAFE_METHODS:
            return False
        return True


def HasRole(*roles):
    """Build a permission class that allows only the given roles. Usage: HasRole(Role.ANALYST, Role.REVIEWER)."""

    class _HasRole(RoleAwareDefault):
        allowed = roles

        def has_permission(self, request, view):
            return super().has_permission(request, view) and request.user.role in self.allowed

    _HasRole.__name__ = "HasRole_" + "_".join(roles)
    return _HasRole


IsAdministrator = HasRole(Role.ADMINISTRATOR)
