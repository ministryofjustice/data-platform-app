from .common import *  # noqa: F401, F403

SECRET_KEY = "test-secret-key-not-for-production"

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Use a fast password hasher so tests with User creation are not slow
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Suppress emails during tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
