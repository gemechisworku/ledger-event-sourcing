"""Canonical stream id builders — must match `src/schema/events.py` headers."""


def loan_stream_id(application_id: str) -> str:
    return f"loan-{application_id}"


def credit_stream_id(application_id: str) -> str:
    return f"credit-{application_id}"


def compliance_stream_id(application_id: str) -> str:
    return f"compliance-{application_id}"


def fraud_stream_id(application_id: str) -> str:
    return f"fraud-{application_id}"


def agent_stream_id(agent_type: str, session_id: str) -> str:
    """agent_type: e.g. AgentType.CREDIT_ANALYSIS.value → 'credit_analysis'"""
    return f"agent-{agent_type}-{session_id}"


def audit_stream_id(entity_type: str, entity_id: str) -> str:
    return f"audit-{entity_type}-{entity_id}"
