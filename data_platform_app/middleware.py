from django.http import HttpResponse


class AllowElbHealthcheckIpHostMiddleware:
    """
    Keep strict host validation for normal traffic.
    For ELB health checks on /healthcheck/, rewrite IP Host headers
    to a canonical allowed host.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthcheck/" and self._is_elb_healthchecker(request):
            return HttpResponse("OK")

        return self.get_response(request)

    @staticmethod
    def _is_elb_healthchecker(request):
        ua = request.META.get("HTTP_USER_AGENT", "")
        return ua.startswith("ELB-HealthChecker/")
