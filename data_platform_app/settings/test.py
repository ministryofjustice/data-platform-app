from .common import *  # noqa: F401, F403

SECRET_KEY = "test-secret-key-not-for-production"

DEBUG = False

# Microsoft Entra is the only auth provider, but the test suite must never hit
# it: tests authenticate with client.force_login, which bypasses the provider.
# Supply dummy AZURE_AUTH credentials so azure_auth imports/boots without a real
# tenant, and use the default ModelBackend so force_login/admin_client stay
# deterministic regardless of any AZURE_* values in the developer's environment.
AZURE_AUTH = {
    **AZURE_AUTH,  # noqa: F405
    "CLIENT_ID": "test-client-id",
    "CLIENT_SECRET": "test-client-secret",
    "REDIRECT_URI": "http://testserver/sso/callback",
    "AUTHORITY": "https://login.microsoftonline.com/test-tenant-id",
}
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# Use a fast password hasher so tests with User creation are not slow
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Suppress emails during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
