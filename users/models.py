from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    """Manager for a user identified by the Entra object id (``oid``).

    On each login ``django-azure-auth`` fetches the user with
    ``get_by_natural_key(oid)``. That method is inherited from
    ``BaseUserManager`` and looks the user up by the ``USERNAME_FIELD``
    (``oid``), so it needs no override. ``create_user``/``create_superuser`` are
    overridden only because the Django defaults expect a ``username`` argument.
    """

    use_in_migrations = True

    def _create_user(self, oid, password=None, **extra_fields):
        if not oid:
            raise ValueError("Users must have an oid")
        email = self.normalize_email(extra_fields.pop("email", "")).lower()
        user = self.model(oid=oid, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, oid=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(oid, password, **extra_fields)

    def create_superuser(self, oid=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(oid, password, **extra_fields)


class User(AbstractUser):
    """Custom user model for future extension."""

    @property
    def full_name(self) -> str:
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    """User identified by the Microsoft Entra object id (``oid``).

    ``oid`` is the login identity (``USERNAME_FIELD``): it is immutable in Entra,
    so a user's email or display name can change without creating a duplicate or
    breaking access. ``username`` is demoted to an optional, human-readable
    display label populated from the Entra ``displayName`` claim.
    """

    oid = models.UUIDField(
        "Entra object ID",
        unique=True,
        help_text="Immutable Microsoft Entra ID object id used as the login identity.",
    )
    username = models.CharField(
        "display name",
        max_length=150,
        blank=True,
        help_text="Human-readable name from Entra; not used to sign in.",
    )

    objects = UserManager()

    USERNAME_FIELD = "oid"
    REQUIRED_FIELDS = []

    def __str__(self) -> str:
        return self.username or self.email or str(self.oid)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)
