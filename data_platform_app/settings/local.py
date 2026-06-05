import os

from .common import *  # noqa

DEBUG = True

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-local-dev-key")

ALLOWED_HOSTS = [".localhost", "127.0.0.1"]

INSTALLED_APPS += [  # noqa
    "debug_toolbar",
]

MIDDLEWARE += [  # noqa
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = [
    "127.0.0.1",
]

# TODO switch this to postgres for local development so dev and prod environments are aligned
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa
    }
}
