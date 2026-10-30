"""The one function every part of DocumentLab uses to write to the audit log."""
from .models import AuditEvent
from .redaction import scrub


def client_ip(request):
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record(request, action: str, obj=None, metadata: dict | None = None, user=None, username: str = ""):
    """Record an action. Sensitive keys in metadata are redacted before saving."""
    actor = user
    if actor is None and request is not None and getattr(request, "user", None) is not None:
        actor = request.user if request.user.is_authenticated else None
    return AuditEvent.objects.create(
        user=actor,
        username=(actor.get_username() if actor else username)[:150],
        action=action,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(getattr(obj, "pk", "") or "") if obj is not None else "",
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:256],
        metadata=scrub(metadata or {}),
    )
