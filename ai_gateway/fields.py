from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def _cipher() -> MultiFernet:
    keys = settings.FIELD_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS is not configured")
    return MultiFernet([Fernet(key) for key in keys])


class EncryptedTextField(models.TextField):
    """A TextField whose value is Fernet-encrypted at rest."""

    def get_db_prep_save(self, value, connection):
        value = super().get_db_prep_save(value, connection)
        if value is None:
            return value
        return _cipher().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return _cipher().decrypt(value.encode()).decode()
