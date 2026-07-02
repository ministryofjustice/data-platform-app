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

# Microsoft Entra is the sole auth provider in every environment, so running
# the app locally requires real AZURE_* credentials in your .env file. The test
# suite does not need them (it uses force_login); see settings/test.py.
