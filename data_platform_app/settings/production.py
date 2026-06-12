from socket import gethostbyname, gethostname

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
