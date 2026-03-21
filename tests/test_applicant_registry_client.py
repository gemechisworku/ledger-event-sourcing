"""
tests/test_applicant_registry_client.py
=======================================
Phase 1.5: ApplicantRegistryClient against PostgreSQL.

Uses APPLICANT_REGISTRY_URL if set, else TEST_DB_URL / DATABASE_URL (same DB as event store is OK).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import asyncpg
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from src.registry.client import ApplicantRegistryClient
from src.registry.schema import REGISTRY_SQL
from tests.pg_helpers import candidate_postgres_urls

TEST_COMPANY_ID = "__pytest_registry_client__"


@pytest.fixture
async def registry_client():
    pool = None
    last_exc: Exception | None = None
    for url in candidate_postgres_urls():
        try:
            pool = await asyncpg.create_pool(url, min_size=1, max_size=2, timeout=10)
            break
        except Exception as exc:
            last_exc = exc
    if pool is None:
        pytest.skip(
            "PostgreSQL not reachable (tried TEST_DB_URL, DATABASE_URL, APPLICANT_REGISTRY_URL, default): "
            f"{last_exc!r}"
        )

    async with pool.acquire() as conn:
        await conn.execute(REGISTRY_SQL)
        await conn.execute(
            "DELETE FROM applicant_registry.loan_relationships WHERE company_id = $1",
            TEST_COMPANY_ID,
        )
        await conn.execute(
            "DELETE FROM applicant_registry.compliance_flags WHERE company_id = $1",
            TEST_COMPANY_ID,
        )
        await conn.execute(
            "DELETE FROM applicant_registry.financial_history WHERE company_id = $1",
            TEST_COMPANY_ID,
        )
        await conn.execute("DELETE FROM applicant_registry.companies WHERE company_id = $1", TEST_COMPANY_ID)

        await conn.execute(
            """INSERT INTO applicant_registry.companies
            (company_id,name,industry,naics,jurisdiction,legal_type,founded_year,employee_count,
             ein,address_city,address_state,relationship_start,account_manager,risk_segment,
             trajectory,submission_channel,ip_region)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
            TEST_COMPANY_ID,
            "Pytest Co",
            "technology",
            "541511",
            "DE",
            "LLC",
            2015,
            42,
            "12-3456789",
            "Wilmington",
            "DE",
            date(2020, 1, 15),
            "mgr",
            "MEDIUM",
            "STABLE",
            "portal",
            "US-East",
        )

        await conn.execute(
            """INSERT INTO applicant_registry.financial_history
            (company_id,fiscal_year,total_revenue,gross_profit,operating_expenses,
             operating_income,ebitda,depreciation_amortization,interest_expense,
             income_before_tax,tax_expense,net_income,total_assets,current_assets,
             cash_and_equivalents,accounts_receivable,inventory,total_liabilities,
             current_liabilities,long_term_debt,total_equity,operating_cash_flow,
             investing_cash_flow,financing_cash_flow,free_cash_flow,debt_to_equity,
             current_ratio,debt_to_ebitda,interest_coverage_ratio,gross_margin,
             ebitda_margin,net_margin,balance_sheet_check)
            VALUES($1,2022,1000000,500000,200000,300000,350000,50000,25000,
             275000,50000,225000,2000000,800000,100000,200000,50000,1200000,
             400000,500000,800000,300000,-50000,-100000,200000,1.5,2.0,3.0,4.0,
             0.5,0.35,0.22,TRUE)""",
            TEST_COMPANY_ID,
        )
        await conn.execute(
            """INSERT INTO applicant_registry.financial_history
            (company_id,fiscal_year,total_revenue,gross_profit,operating_expenses,
             operating_income,ebitda,depreciation_amortization,interest_expense,
             income_before_tax,tax_expense,net_income,total_assets,current_assets,
             cash_and_equivalents,accounts_receivable,inventory,total_liabilities,
             current_liabilities,long_term_debt,total_equity,operating_cash_flow,
             investing_cash_flow,financing_cash_flow,free_cash_flow,debt_to_equity,
             current_ratio,debt_to_ebitda,interest_coverage_ratio,gross_margin,
             ebitda_margin,net_margin,balance_sheet_check)
            VALUES($1,2023,1100000,550000,210000,310000,360000,52000,26000,
             284000,52000,232000,2100000,820000,110000,210000,52000,1250000,
             410000,510000,850000,310000,-52000,-102000,206000,1.47,2.1,3.1,4.1,
             0.52,0.36,0.23,TRUE)""",
            TEST_COMPANY_ID,
        )

        await conn.execute(
            """INSERT INTO applicant_registry.compliance_flags
            (company_id,flag_type,severity,is_active,added_date,note)
            VALUES($1,'AML_WATCH','HIGH',TRUE,$2,'test flag')""",
            TEST_COMPANY_ID,
            date(2024, 6, 1),
        )
        await conn.execute(
            """INSERT INTO applicant_registry.compliance_flags
            (company_id,flag_type,severity,is_active,added_date,note)
            VALUES($1,'PEP_LINK','LOW',FALSE,$2,'cleared')""",
            TEST_COMPANY_ID,
            date(2023, 1, 1),
        )

        await conn.execute(
            """INSERT INTO applicant_registry.loan_relationships
            (company_id,loan_amount,loan_year,was_repaid,default_occurred,note)
            VALUES($1,250000.00,2021,TRUE,FALSE,'term loan')""",
            TEST_COMPANY_ID,
        )

    client = ApplicantRegistryClient(pool)
    yield client

    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM applicant_registry.loan_relationships WHERE company_id = $1",
            TEST_COMPANY_ID,
        )
        await conn.execute(
            "DELETE FROM applicant_registry.compliance_flags WHERE company_id = $1",
            TEST_COMPANY_ID,
        )
        await conn.execute(
            "DELETE FROM applicant_registry.financial_history WHERE company_id = $1",
            TEST_COMPANY_ID,
        )
        await conn.execute("DELETE FROM applicant_registry.companies WHERE company_id = $1", TEST_COMPANY_ID)
    await pool.close()


@pytest.mark.asyncio
async def test_get_company(registry_client: ApplicantRegistryClient):
    co = await registry_client.get_company(TEST_COMPANY_ID)
    assert co is not None
    assert co.name == "Pytest Co"
    assert co.risk_segment == "MEDIUM"
    assert co.naics == "541511"


@pytest.mark.asyncio
async def test_get_company_missing(registry_client: ApplicantRegistryClient):
    assert await registry_client.get_company("no-such-id") is None


@pytest.mark.asyncio
async def test_get_financial_history_all_years(registry_client: ApplicantRegistryClient):
    rows = await registry_client.get_financial_history(TEST_COMPANY_ID)
    assert len(rows) == 2
    assert rows[0].fiscal_year == 2022
    assert rows[1].fiscal_year == 2023
    assert rows[0].total_revenue == 1_000_000.0


@pytest.mark.asyncio
async def test_get_financial_history_filter_years(registry_client: ApplicantRegistryClient):
    rows = await registry_client.get_financial_history(TEST_COMPANY_ID, years=[2023])
    assert len(rows) == 1
    assert rows[0].fiscal_year == 2023


@pytest.mark.asyncio
async def test_get_compliance_flags(registry_client: ApplicantRegistryClient):
    all_flags = await registry_client.get_compliance_flags(TEST_COMPANY_ID)
    assert len(all_flags) == 2
    active = await registry_client.get_compliance_flags(TEST_COMPANY_ID, active_only=True)
    assert len(active) == 1
    assert active[0].flag_type == "AML_WATCH"
    assert active[0].is_active is True


@pytest.mark.asyncio
async def test_get_loan_relationships(registry_client: ApplicantRegistryClient):
    loans = await registry_client.get_loan_relationships(TEST_COMPANY_ID)
    assert len(loans) == 1
    assert loans[0]["loan_year"] == 2021
    assert loans[0]["was_repaid"] is True
    assert loans[0]["loan_amount"] == 250_000.0
