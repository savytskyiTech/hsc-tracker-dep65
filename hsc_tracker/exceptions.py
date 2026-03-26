class SessionExpiredError(Exception):
    """Raised when the authenticated HSC session is no longer valid."""


class RateLimitedError(Exception):
    """Raised when remote service indicates too many requests / rate limiting."""
