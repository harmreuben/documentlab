from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    ADMINISTRATOR = "ADMINISTRATOR", "Administrator"
    ANALYST = "ANALYST", "Analyst"
    REVIEWER = "REVIEWER", "Reviewer"
    DEVELOPER = "DEVELOPER", "Developer"
    READ_ONLY = "READ_ONLY", "Read-only user"


class DocumentLabUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMINISTRATOR)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """A DocumentLab user. Every user has exactly one role; new users start read-only."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.READ_ONLY)

    objects = DocumentLabUserManager()

    def has_role(self, *roles: str) -> bool:
        return self.is_active and self.role in roles

    @property
    def is_administrator(self) -> bool:
        return self.has_role(Role.ADMINISTRATOR)

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"
