class NotFoundError(Exception):
    """Raised when a referenced record does not exist."""


class InsufficientFundsError(Exception):
    """Raised when a debit would take an account's balance negative."""


class InvalidStatusTransitionError(Exception):
    """Raised when a service request status change isn't a valid transition."""


class ValidationError(Exception):
    """Raised when input fails a business-rule validation check."""


class SessionOwnershipError(Exception):
    """Raised when a client-chosen session_id is reused by an authenticated
    customer other than the one who first used it - session_id has no
    identity binding of its own, so without this check two customers could
    collide on the same thread and see each other's conversation state."""
