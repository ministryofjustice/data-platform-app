import logging
from collections.abc import Callable
from contextvars import ContextVar
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

_REQUEST_ID_CTX_VAR: ContextVar[str] = ContextVar("request_id", default="-")
_REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> str:
    """Return the current request identifier for logging context."""
    return _REQUEST_ID_CTX_VAR.get()


class RequestIdLoggingFilter(logging.Filter):
    """Attach request_id to every log record for formatter use."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RequestIdMiddleware:
    """Set request_id on each request and return it as a response header."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = uuid4().hex

        token = _REQUEST_ID_CTX_VAR.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _REQUEST_ID_CTX_VAR.reset(token)

        response[_REQUEST_ID_HEADER] = request_id
        return response
