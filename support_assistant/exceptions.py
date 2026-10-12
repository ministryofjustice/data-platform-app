"""Exceptions raised by the support assistant."""


class SupportAssistantError(Exception):
    """Base class for support assistant errors."""


class GuideFetchError(SupportAssistantError):
    """Raised when the user guide cannot be downloaded from GitHub."""
