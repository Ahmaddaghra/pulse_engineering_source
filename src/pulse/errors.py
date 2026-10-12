class PolicyBlocked(RuntimeError):
    """Authorization cannot be established; no content may be accepted."""


class StaleLease(RuntimeError):
    """A worker no longer holds the current unexpired fencing token."""
