"""Exceptions raised by the AI Gateway client."""


class AIGatewayError(Exception):
    """Base class for all AI Gateway client errors."""


class AIGatewayAPIError(AIGatewayError):
    """Raised when the AI Gateway returns a non-success HTTP response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"AI Gateway returned {status_code}: {message}")


class AIGatewayTransportError(AIGatewayError):
    """Raised when requests to the AI Gateway fail before a response is received."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"AI Gateway transport failure: {message}")
