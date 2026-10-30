from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .services import record


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record(request, "auth.login", user, user=user)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        record(request, "auth.logout", user, user=user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # Only the username is kept - Django already masks the password, and we never store it.
    record(request, "auth.login_failed", username=str(credentials.get("username", ""))[:150])
