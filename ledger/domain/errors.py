"""Domain-level validation errors (business rules)."""


class DomainError(Exception):
    """Raised when an invariant or business rule is violated."""
