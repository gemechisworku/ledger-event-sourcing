"""ComplianceRecord aggregate — stream `compliance-{application_id}`."""

from __future__ import annotations

from typing import Any

from ledger.domain.errors import DomainError
from ledger.domain.streams import compliance_stream_id


class ComplianceRecordAggregate:
    """Tracks mandatory rules and pass/fail for ApplicationApproved precondition."""

    def __init__(self, application_id: str) -> None:
        self.application_id = application_id
        self.version: int = 0
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

    def _apply(self, event: dict) -> None:
        et = event["event_type"]
        p = event.get("payload", {})
        self.version = int(event["stream_position"])

        if et == "ComplianceCheckInitiated":
            self.required_rules = list(p.get("rules_to_evaluate", []))
            self.regulation_set_version = p.get("regulation_set_version")
        elif et == "ComplianceRulePassed":
            self.passed_rules.add(p.get("rule_id", ""))
        elif et == "ComplianceRuleFailed":
            if p.get("is_hard_block"):
                self.failed_hard_block = True

    def assert_all_required_passed(self) -> None:
        if not self.required_rules:
            raise DomainError("ComplianceCheckInitiated (required rules) missing before approval")
        missing = [r for r in self.required_rules if r not in self.passed_rules]
        if missing:
            raise DomainError(f"Compliance rules not all passed; missing: {missing}")
        if self.failed_hard_block:
            raise DomainError("Compliance has a hard-block failure; cannot approve")
