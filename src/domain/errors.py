"""Domain-level validation errors (business rules)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DomainError(Exception):
    """Raised when an invariant or business rule is violated."""
    message: str
    aggregate_id: str | None = field(default=None)
    rule: str | None = field(default=None)

    def __str__(self) -> str:
        return self.message
