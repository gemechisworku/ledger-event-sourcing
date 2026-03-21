"""
src/registry/client.py — Applicant Registry read-only client
===============================================================
Reads from the `applicant_registry` schema in PostgreSQL (CRM / datagen seed).
READ-ONLY — no writes from the event-sourced ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import asyncpg

__all__ = [
    "ApplicantRegistryClient",
    "CompanyProfile",
    "FinancialYear",
    "ComplianceFlag",
]


def _nf(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    return float(v)


def _date_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


@dataclass
class CompanyProfile:
    company_id: str
    name: str
    industry: str
    naics: str
    jurisdiction: str
    legal_type: str
    founded_year: int
    employee_count: int
    risk_segment: str
    trajectory: str
    submission_channel: str
    ip_region: str


@dataclass
class FinancialYear:
    fiscal_year: int
    total_revenue: float
    gross_profit: float
    operating_income: float
    ebitda: float
    net_income: float
    total_assets: float
    total_liabilities: float
    total_equity: float
    long_term_debt: float
    cash_and_equivalents: float
    current_assets: float
    current_liabilities: float
    accounts_receivable: float
    inventory: float
    debt_to_equity: float
    current_ratio: float
    debt_to_ebitda: float
    interest_coverage_ratio: float
    gross_margin: float
    ebitda_margin: float
    net_margin: float


@dataclass
class ComplianceFlag:
    flag_type: str
    severity: str
    is_active: bool
    added_date: str
    note: str


def _row_to_company(row: asyncpg.Record) -> CompanyProfile:
    return CompanyProfile(
        company_id=row["company_id"],
        name=row["name"],
        industry=row["industry"],
        naics=row["naics"],
        jurisdiction=row["jurisdiction"],
        legal_type=row["legal_type"],
        founded_year=int(row["founded_year"]),
        employee_count=int(row["employee_count"]),
        risk_segment=row["risk_segment"],
        trajectory=row["trajectory"],
        submission_channel=row["submission_channel"],
        ip_region=row["ip_region"],
    )


def _row_to_financial_year(row: asyncpg.Record) -> FinancialYear:
    return FinancialYear(
        fiscal_year=int(row["fiscal_year"]),
        total_revenue=_nf(row["total_revenue"]),
        gross_profit=_nf(row["gross_profit"]),
        operating_income=_nf(row["operating_income"]),
        ebitda=_nf(row["ebitda"]),
        net_income=_nf(row["net_income"]),
        total_assets=_nf(row["total_assets"]),
        total_liabilities=_nf(row["total_liabilities"]),
        total_equity=_nf(row["total_equity"]),
        long_term_debt=_nf(row["long_term_debt"]),
        cash_and_equivalents=_nf(row["cash_and_equivalents"]),
        current_assets=_nf(row["current_assets"]),
        current_liabilities=_nf(row["current_liabilities"]),
        accounts_receivable=_nf(row["accounts_receivable"]),
        inventory=_nf(row["inventory"]),
        debt_to_equity=_nf(row["debt_to_equity"]),
        current_ratio=_nf(row["current_ratio"]),
        debt_to_ebitda=_nf(row["debt_to_ebitda"]),
        interest_coverage_ratio=_nf(row["interest_coverage_ratio"]),
        gross_margin=_nf(row["gross_margin"]),
        ebitda_margin=_nf(row["ebitda_margin"]),
        net_margin=_nf(row["net_margin"]),
    )


def _row_to_compliance_flag(row: asyncpg.Record) -> ComplianceFlag:
    return ComplianceFlag(
        flag_type=row["flag_type"],
        severity=row["severity"],
        is_active=bool(row["is_active"]),
        added_date=_date_str(row["added_date"]),
        note=row["note"] or "",
    )


class ApplicantRegistryClient:
    """
    READ-ONLY access to the Applicant Registry.
    Agents call these methods to get company profiles and historical data.
    Never write to this database from the event store system.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_company(self, company_id: str) -> CompanyProfile | None:
        q = """
            SELECT company_id, name, industry, naics, jurisdiction, legal_type, founded_year,
                   employee_count, risk_segment, trajectory, submission_channel, ip_region
            FROM applicant_registry.companies
            WHERE company_id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, company_id)
        return _row_to_company(row) if row else None

    async def get_financial_history(
        self,
        company_id: str,
        years: list[int] | None = None,
    ) -> list[FinancialYear]:
        base = """
            SELECT fiscal_year, total_revenue, gross_profit, operating_income, ebitda, net_income,
                   total_assets, total_liabilities, total_equity, long_term_debt, cash_and_equivalents,
                   current_assets, current_liabilities, accounts_receivable, inventory,
                   debt_to_equity, current_ratio, debt_to_ebitda, interest_coverage_ratio,
                   gross_margin, ebitda_margin, net_margin
            FROM applicant_registry.financial_history
            WHERE company_id = $1
        """
        async with self._pool.acquire() as conn:
            if years:
                rows = await conn.fetch(
                    base + " AND fiscal_year = ANY($2::int[]) ORDER BY fiscal_year ASC",
                    company_id,
                    years,
                )
            else:
                rows = await conn.fetch(base + " ORDER BY fiscal_year ASC", company_id)
        return [_row_to_financial_year(r) for r in rows]

    async def get_compliance_flags(
        self,
        company_id: str,
        active_only: bool = False,
    ) -> list[ComplianceFlag]:
        q = """
            SELECT flag_type, severity, is_active, added_date, note
            FROM applicant_registry.compliance_flags
            WHERE company_id = $1
        """
        if active_only:
            q += " AND is_active = TRUE"
        q += " ORDER BY added_date ASC, id ASC"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, company_id)
        return [_row_to_compliance_flag(r) for r in rows]

    async def get_loan_relationships(self, company_id: str) -> list[dict[str, Any]]:
        q = """
            SELECT id, company_id, loan_amount, loan_year, was_repaid, default_occurred, note
            FROM applicant_registry.loan_relationships
            WHERE company_id = $1
            ORDER BY loan_year ASC, id ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(q, company_id)
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": int(r["id"]),
                    "company_id": r["company_id"],
                    "loan_amount": _nf(r["loan_amount"]),
                    "loan_year": int(r["loan_year"]),
                    "was_repaid": bool(r["was_repaid"]),
                    "default_occurred": bool(r["default_occurred"]),
                    "note": r["note"] or "",
                }
            )
        return out
