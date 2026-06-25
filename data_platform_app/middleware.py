from ipaddress import ip_address

import structlog
from django.conf import settings

logger = structlog.get_logger(__name__)


class AllowElbHealthcheckIpHostMiddleware:
    """
    Keep strict host validation for normal traffic.
    For ELB health checks on /healthcheck/, rewrite IP Host headers
    to a canonical allowed host.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Pick a stable, explicit host from settings.
        configured = getattr(settings, "HEALTHCHECK_CANONICAL_HOST", "")
        if configured:
            self.canonical_host = configured
        else:
            # Fallback: first non-wildcard non-suffix host in ALLOWED_HOSTS.
            self.canonical_host = next(
                (
                    h
                    for h in settings.ALLOWED_HOSTS
                    if h not in {"*", ""} and not h.startswith(".")
                ),
                "localhost",
            )

    def __call__(self, request):
        if request.path == "/healthcheck/" and self._is_elb_healthchecker(request):
            host = request.META.get("HTTP_HOST", "")
            forwarded_host = request.META.get("HTTP_X_FORWARDED_HOST", "")
            logger.info(
                "elb healthcheck headers before",
                host=host,
                forwarded_host=forwarded_host,
            )
            rewrote = False
            host_only = host.split(":", 1)[0]
            if self._is_ip(host_only):
                # Prevent forwarded host from taking precedence.
                request.META.pop("HTTP_X_FORWARDED_HOST", None)
                request.META["HTTP_HOST"] = self.canonical_host
                rewrote = True

            logger.info(
                "elb healthcheck headers after",
                host=request.META.get("HTTP_HOST", ""),
                forwarded_host=request.META.get("HTTP_X_FORWARDED_HOST", ""),
                rewrote_host=rewrote,
                canonical_host=self.canonical_host,
            )
        return self.get_response(request)

    @staticmethod
    def _is_elb_healthchecker(request):
        ua = request.META.get("HTTP_USER_AGENT", "")
        return ua.startswith("ELB-HealthChecker/")

    @staticmethod
    def _is_ip(value):
        try:
            ip_address(value)
            return True
        except ValueError:
            return False
