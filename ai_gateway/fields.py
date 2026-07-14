from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.functional import cached_property


class EncryptedTextField(models.TextField):
    """A TextField whose value is Fernet-encrypted at rest."""

    @cached_property
    def _cipher(self) -> MultiFernet:
        keys = settings.FIELD_ENCRYPTION_KEYS
        if not keys:
            raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS is not configured")
        return MultiFernet([Fernet(key) for key in keys])

    def get_db_prep_save(self, value, connection):
        value = super().get_db_prep_save(value, connection)
        if value is None:
            return value
        return self._cipher.encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self._cipher.decrypt(value.encode()).decode()
