import os

from .common import *  # noqa
from .common import E2E_AUTH_ENABLED

DEBUG = not E2E_AUTH_ENABLED

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-local-dev-key")

ALLOWED_HOSTS = [".localhost", "127.0.0.1"]

if not E2E_AUTH_ENABLED:
    INSTALLED_APPS += [  # noqa
        "debug_toolbar",
    ]

    MIDDLEWARE += [  # noqa
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ]

INTERNAL_IPS = [
    "127.0.0.1",
]
