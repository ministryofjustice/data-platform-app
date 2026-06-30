import ipaddress
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy

HEALTHCHECK_PATH = reverse_lazy("healthcheck")
ELB_HEALTHCHECKER_PREFIX = "ELB-HealthChecker"


class HealthCheckHostMiddleware:
    """Allow ALB health checks that arrive with an IP ``Host`` header.

    ALB target-group health checks (``targetType: instance`` over NodePort with
    a Cilium overlay) reach Django with ``Host`` set to a node/overlay IP that is
    not in ``ALLOWED_HOSTS``, so Django rejects them with a 400. ALB target-group
    health checks cannot send a custom ``Host`` header, so this is handled in the
    app.

    This middleware short-circuits and returns ``200`` only for genuine ALB
    health checks, identified by all of:

    * request path is the ``healthcheck`` URL
    * ``User-Agent`` begins with ``ELB-HealthChecker``
    * the raw ``Host`` header is an IP address

    It never mutates the ``Host`` header and never calls ``get_host()``, so strict
    host validation is preserved for every other request. The ``User-Agent`` check
    is only a narrowing filter, not a trust signal: the response is a constant
    ``OK`` with no side effects, so a spoofed health check gains nothing.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self._is_elb_healthcheck(request):
            return HttpResponse("OK")
        return self.get_response(request)

    def _is_elb_healthcheck(self, request: HttpRequest) -> bool:
        if request.path != HEALTHCHECK_PATH:
            return False

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        if not user_agent.startswith(ELB_HEALTHCHECKER_PREFIX):
            return False

        return self._host_is_ip(request.META.get("HTTP_HOST", ""))

    @staticmethod
    def _host_is_ip(host: str) -> bool:
        if not host:
            return False

        # Strip an optional port. IPv6 literals are bracketed, e.g.
        # "[::1]:8000"; IPv4 hosts carry a single ":port" suffix.
        if host.startswith("[") and "]" in host:
            host = host[1 : host.index("]")]
        elif host.count(":") == 1:
            host = host.split(":", 1)[0]

        try:
            ipaddress.ip_address(host)
        except ValueError:
            return False
        return True
