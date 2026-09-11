class NotFoundError(Exception):
    """Raised when a referenced record does not exist."""


class InsufficientFundsError(Exception):
    """Raised when a debit would take an account's balance negative."""


class InvalidStatusTransitionError(Exception):
    """Raised when a service request status change isn't a valid transition."""


class ValidationError(Exception):
    """Raised when input fails a business-rule validation check."""
