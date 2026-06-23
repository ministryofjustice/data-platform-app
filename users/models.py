from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model for future extension."""

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()
