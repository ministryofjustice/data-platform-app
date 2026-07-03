from .common import *  # noqa: F401, F403

SECRET_KEY = "test-secret-key-not-for-production"

DEBUG = False

# Pin AZURE_AUTH to dummy values and use ModelBackend so the suite is deterministic
# regardless of any AZURE_* values in the developer's environment. No test exercises
# the provider views, so real credentials are never read.
AZURE_AUTH = {
    **AZURE_AUTH,  # noqa: F405
    "CLIENT_ID": "test-client-id",
    "CLIENT_SECRET": "test-client-secret",
    "REDIRECT_URI": "http://testserver/sso/callback/",
    "AUTHORITY": "https://login.microsoftonline.com/test-tenant-id",
}
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# Use a fast password hasher so tests with User creation are not slow
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Suppress emails during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Use non-manifest static storage in tests so static lookups do not require collectstatic.
STORAGES["staticfiles"] = {  # type: ignore[index]  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}
