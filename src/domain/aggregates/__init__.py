"""Compatibility shim — canonical aggregates: `src.aggregates`."""

from src.aggregates import (
    AgentSessionAggregate,
    AuditLedgerAggregate,
    ComplianceRecordAggregate,
    LoanApplicationAggregate,
)

__all__ = [
    "AgentSessionAggregate",
    "AuditLedgerAggregate",
    "ComplianceRecordAggregate",
    "LoanApplicationAggregate",
]
