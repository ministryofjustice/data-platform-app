from collections.abc import Callable
from uuid import uuid4

from django.http import HttpRequest, HttpResponse
from structlog.contextvars import bind_contextvars, unbind_contextvars

_REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_META_KEY = "HTTP_X_REQUEST_ID"


class RequestIdMiddleware:
    """Ensure each request has a request_id and expose it as a response header."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get(_REQUEST_ID_META_KEY) or uuid4().hex
        request.META[_REQUEST_ID_META_KEY] = request_id
        request.request_id = request_id

        bind_contextvars(request_id=request_id)
        try:
            response = self.get_response(request)
        finally:
            unbind_contextvars("request_id")

        response[_REQUEST_ID_HEADER] = request_id
        return response
