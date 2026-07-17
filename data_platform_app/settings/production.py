import os
from socket import gethostbyname, gethostname

import sentry_sdk

from .common import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = ["data-platform.service.justice.gov.uk"]

ALLOWED_HOSTS.append(gethostbyname(gethostname()))


# -- HTTP headers
# Sets the X-Content-Type-Options: nosniff header
SECURE_CONTENT_TYPE_NOSNIFF = True

# Secure the CSRF cookie
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# Secure the session cookie
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True

# Use the X-Forwarded-Proto header to determine if the request is secure
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        # Add data like request headers and IP for users;
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        environment=os.environ.get("APP_ENV", "production"),
    )
