"""ComplianceRecord aggregate — stream `compliance-{application_id}`.

Uses per-event dispatch: _apply delegates to _on_{EventType} methods.
"""

from __future__ import annotations

from typing import Any

from src.domain.errors import DomainError
from src.domain.streams import compliance_stream_id
from src.models.events import StoredEvent


class ComplianceRecordAggregate:
    """Tracks mandatory rules and pass/fail for ApplicationApproved precondition."""

    def __init__(self, application_id: str) -> None:
        self.application_id = application_id
        self.version: int = -1
        self.required_rules: list[str] = []
        self.passed_rules: set[str] = set()
        self.failed_hard_block: bool = False
        self.regulation_set_version: str | None = None

    @property
    def stream_id(self) -> str:
        return compliance_stream_id(self.application_id)

    @classmethod
    async def load(cls, store: Any, application_id: str) -> ComplianceRecordAggregate:
        agg = cls(application_id=application_id)
        events = await store.load_stream(agg.stream_id)
        for ev in events:
            agg._apply(ev)
        agg.version = await store.stream_version(agg.stream_id)
        return agg

    def _apply(self, event: StoredEvent) -> None:
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)
        self.version = event.stream_position

    def _on_ComplianceCheckInitiated(self, event: StoredEvent) -> None:
        self.required_rules = list(event.payload.get("rules_to_evaluate", []))
        self.regulation_set_version = event.payload.get("regulation_set_version")

    def _on_ComplianceRulePassed(self, event: StoredEvent) -> None:
        self.passed_rules.add(event.payload.get("rule_id", ""))

    def _on_ComplianceRuleFailed(self, event: StoredEvent) -> None:
        if event.payload.get("is_hard_block"):
            self.failed_hard_block = True

    # ── Guards ──

    def assert_all_required_passed(self) -> None:
        if not self.required_rules:
            raise DomainError("ComplianceCheckInitiated (required rules) missing before approval")
        missing = [r for r in self.required_rules if r not in self.passed_rules]
        if missing:
            raise DomainError(f"Compliance rules not all passed; missing: {missing}")
        if self.failed_hard_block:
            raise DomainError("Compliance has a hard-block failure; cannot approve")
