"""
Seed applicant_registry from data/applicant_profiles.json, optional demo loan stream + documents,
then catch up application_summary projection.

Usage:
  uv run python scripts/seed_dev_stack.py
  uv run python scripts/seed_dev_stack.py --db-url postgresql://postgres:apex@localhost:5432/apex_ledger
  uv run python scripts/seed_dev_stack.py --skip-demo --profiles data/applicant_profiles.json

Docker (from host):
  docker compose exec api uv run python scripts/seed_dev_stack.py
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

import asyncpg

from src.domain.handlers import handle_submit_application
from src.domain.streams import loan_stream_id
from src.event_store import EventStore
from src.projections import ApplicationSummaryProjection, ProjectionDaemon
from src.registry.schema import REGISTRY_SQL
from src.schema.events import DocumentFormat, DocumentType, DocumentUploaded, LoanPurpose
from src.upcasters import default_upcaster_registry


DEMO_APPLICATION_ID = "APEX-0001"
DEMO_APPLICANT_ID = "COMP-001"


def _registry_statements() -> list[str]:
    parts: list[str] = []
    for chunk in REGISTRY_SQL.split(";"):
        stmt = chunk.strip()
        if stmt:
            parts.append(stmt)
    return parts


def _ein_for(company_id: str) -> str:
    h = hashlib.sha256(company_id.encode()).hexdigest()
    digits = "".join(c for c in h if c.isdigit())[:9].ljust(9, "0")
    return f"{digits[:2]}-{digits[2:]}"


def _naics_for(industry: str) -> str:
    m = {
        "construction": "236220",
        "retail": "452210",
        "technology": "541511",
        "logistics": "484110",
        "other": "999990",
    }
    return m.get(industry.lower(), "541990")


def _city_state(jurisdiction: str) -> tuple[str, str]:
    # jurisdiction is often a US state code in profiles
    code = (jurisdiction or "DE")[:2].upper()
    cities = {"VA": "Richmond", "OR": "Portland", "IL": "Chicago", "DE": "Wilmington"}
    return cities.get(code, "Wilmington"), code


def _risk_segment(raw: str) -> str:
    u = (raw or "MEDIUM").upper()
    if u not in ("LOW", "MEDIUM", "HIGH"):
        return "MEDIUM"
    return u


async def seed_registry(
    conn: asyncpg.Connection,
    profiles: list[dict],
) -> None:
    for stmt in _registry_statements():
        await conn.execute(stmt)

    for p in profiles:
        cid = p["company_id"]
        name = p["name"]
        industry = p.get("industry") or "technology"
        jurisdiction = p.get("jurisdiction") or "DE"
        legal_type = p.get("legal_type") or "LLC"
        trajectory = (p.get("trajectory") or "STABLE").upper()
        risk = _risk_segment(p.get("risk_segment", "MEDIUM"))
        city, st = _city_state(jurisdiction)
        naics = _naics_for(industry)
        ein = _ein_for(cid)
        h = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16)
        founded = 1990 + (h % 30)
        employees = 10 + (h % 500)
        rel = date(2018 + (h % 5), 1 + (h % 11), 1 + (h % 27))

        await conn.execute(
            """
            INSERT INTO applicant_registry.companies
            (company_id, name, industry, naics, jurisdiction, legal_type, founded_year, employee_count,
             ein, address_city, address_state, relationship_start, account_manager, risk_segment,
             trajectory, submission_channel, ip_region)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (company_id) DO UPDATE SET
              name = EXCLUDED.name,
              industry = EXCLUDED.industry,
              naics = EXCLUDED.naics,
              jurisdiction = EXCLUDED.jurisdiction,
              legal_type = EXCLUDED.legal_type,
              founded_year = EXCLUDED.founded_year,
              employee_count = EXCLUDED.employee_count,
              ein = EXCLUDED.ein,
              address_city = EXCLUDED.address_city,
              address_state = EXCLUDED.address_state,
              relationship_start = EXCLUDED.relationship_start,
              account_manager = EXCLUDED.account_manager,
              risk_segment = EXCLUDED.risk_segment,
              trajectory = EXCLUDED.trajectory,
              submission_channel = EXCLUDED.submission_channel,
              ip_region = EXCLUDED.ip_region
            """,
            cid,
            name,
            industry,
            naics,
            jurisdiction,
            legal_type,
            founded,
            employees,
            ein,
            city,
            st,
            rel,
            "seed-script",
            risk,
            trajectory,
            "web",
            "US-East",
        )

        await conn.execute(
            "DELETE FROM applicant_registry.financial_history WHERE company_id = $1",
            cid,
        )
        base_rev = 1_000_000 + (h % 500_000)
        for year_offset, fy in enumerate((2022, 2023, 2024)):
            rev = Decimal(str(base_rev + year_offset * 50_000))
            await conn.execute(
                """
                INSERT INTO applicant_registry.financial_history
                (company_id,fiscal_year,total_revenue,gross_profit,operating_expenses,
                 operating_income,ebitda,depreciation_amortization,interest_expense,
                 income_before_tax,tax_expense,net_income,total_assets,current_assets,
                 cash_and_equivalents,accounts_receivable,inventory,total_liabilities,
                 current_liabilities,long_term_debt,total_equity,operating_cash_flow,
                 investing_cash_flow,financing_cash_flow,free_cash_flow,debt_to_equity,
                 current_ratio,debt_to_ebitda,interest_coverage_ratio,gross_margin,
                 ebitda_margin,net_margin,balance_sheet_check)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                       $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33)
                """,
                cid,
                fy,
                rev,
                rev * Decimal("0.5"),
                rev * Decimal("0.2"),
                rev * Decimal("0.12"),
                rev * Decimal("0.15"),
                rev * Decimal("0.02"),
                rev * Decimal("0.015"),
                rev * Decimal("0.1"),
                rev * Decimal("0.02"),
                rev * Decimal("0.08"),
                rev * Decimal("2.0"),
                rev * Decimal("0.8"),
                rev * Decimal("0.1"),
                rev * Decimal("0.15"),
                rev * Decimal("0.05"),
                rev * Decimal("1.2"),
                rev * Decimal("0.4"),
                rev * Decimal("0.5"),
                rev * Decimal("0.8"),
                rev * Decimal("0.1"),
                rev * Decimal("-0.02"),
                rev * Decimal("-0.01"),
                rev * Decimal("0.09"),
                Decimal("1.5"),
                Decimal("2.0"),
                Decimal("3.0"),
                Decimal("4.0"),
                Decimal("0.5"),
                Decimal("0.15"),
                Decimal("0.08"),
                True,
            )


def _file_sha16(path: Path) -> str:
    if not path.is_file():
        return "0" * 16
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _demo_document_specs(repo_root: Path) -> list[tuple[str, DocumentType, DocumentFormat, str]]:
    """Relative path under repo (documents/...), types, filename for events."""
    comp = repo_root / "documents" / DEMO_APPLICANT_ID
    specs: list[tuple[str, DocumentType, DocumentFormat, str]] = []
    mapping: list[tuple[str, DocumentType, DocumentFormat]] = [
        ("application_proposal.pdf", DocumentType.APPLICATION_PROPOSAL, DocumentFormat.PDF),
        ("income_statement_2024.pdf", DocumentType.INCOME_STATEMENT, DocumentFormat.PDF),
        ("balance_sheet_2024.pdf", DocumentType.BALANCE_SHEET, DocumentFormat.PDF),
        ("financial_statements.xlsx", DocumentType.INCOME_STATEMENT, DocumentFormat.XLSX),
        ("financial_summary.csv", DocumentType.BANK_STATEMENTS, DocumentFormat.CSV),
    ]
    for fname, dtype, fmt in mapping:
        rel = f"documents/{DEMO_APPLICANT_ID}/{fname}"
        if (comp / fname).is_file():
            specs.append((rel, dtype, fmt, fname))
    return specs


async def seed_demo_application(store: EventStore, repo_root: Path) -> None:
    from src.domain.aggregates.loan_application import LoanApplicationAggregate

    sid = loan_stream_id(DEMO_APPLICATION_ID)
    existing = await store.load_stream(sid)
    has_submit = any(e.event_type == "ApplicationSubmitted" for e in existing)

    if not has_submit:
        await handle_submit_application(
            store,
            application_id=DEMO_APPLICATION_ID,
            applicant_id=DEMO_APPLICANT_ID,
            requested_amount_usd=Decimal("250000"),
            loan_purpose=LoanPurpose.WORKING_CAPITAL,
            loan_term_months=36,
            submission_channel="web",
            contact_email="seed@example.com",
            contact_name="Seed User",
            application_reference="seed_dev_stack",
        )
        print(f"  [demo] ApplicationSubmitted on {sid}")

    specs = _demo_document_specs(repo_root)
    if not specs:
        print("  [demo] No files under documents/COMP-001/ — skipping DocumentUploaded")
        return

    existing = await store.load_stream(sid)
    doc_count = sum(1 for e in existing if e.event_type == "DocumentUploaded")
    if doc_count >= len(specs):
        print(f"  [demo] DocumentUploaded already present ({doc_count}); skipping")
        return

    agg = await LoanApplicationAggregate.load(store, DEMO_APPLICATION_ID)
    evs: list[dict] = []
    now = datetime.now(timezone.utc)
    for rel, dtype, fmt, fname in specs:
        fp = repo_root / rel
        sz = fp.stat().st_size if fp.is_file() else 0
        du = DocumentUploaded(
            application_id=DEMO_APPLICATION_ID,
            document_id=f"doc-{uuid4().hex[:12]}",
            document_type=dtype,
            document_format=fmt,
            filename=fname,
            file_path=rel.replace("\\", "/"),
            file_size_bytes=sz,
            file_hash=_file_sha16(fp),
            fiscal_year=2024 if dtype != DocumentType.APPLICATION_PROPOSAL else None,
            uploaded_at=now,
            uploaded_by="seed_dev_stack",
        )
        evs.append(du.to_store_dict())

    await store.append(sid, evs, expected_version=agg.version)
    print(f"  [demo] Appended {len(evs)} DocumentUploaded event(s) to {sid}")


async def catch_up_application_summary(store: EventStore) -> None:
    proj = ApplicationSummaryProjection(store)
    daemon = ProjectionDaemon(store, [proj])
    total = 0
    for _ in range(200):
        n = await daemon.process_batch()
        total += n
        if n == 0:
            break
    if total == 0:
        print("  [projection] application_summary: no new events (checkpoint already caught up)")
    else:
        print(f"  [projection] application_summary processed ~{total} event(s)")


async def async_main() -> None:
    p = argparse.ArgumentParser(description="Seed applicant registry + optional UI demo application")
    p.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL") or os.environ.get("TEST_DB_URL"),
        help="PostgreSQL URL (default: DATABASE_URL)",
    )
    p.add_argument(
        "--profiles",
        type=Path,
        default=_ROOT / "data" / "applicant_profiles.json",
        help="Path to applicant_profiles.json",
    )
    p.add_argument("--skip-registry", action="store_true", help="Skip applicant_registry seed")
    p.add_argument("--skip-demo", action="store_true", help="Skip demo loan stream + documents")
    args = p.parse_args()

    if not args.db_url:
        raise SystemExit("DATABASE_URL or --db-url required")

    repo_root = _ROOT

    if not args.skip_registry:
        raw = json.loads(args.profiles.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise SystemExit("--profiles must be a JSON array")
        print(f"[registry] Loading {len(raw)} profile(s) from {args.profiles}")
        conn = await asyncpg.connect(args.db_url)
        try:
            await seed_registry(conn, raw)
        finally:
            await conn.close()
        print(f"  [registry] Upserted companies + financial_history for {len(raw)} id(s)")

    if args.skip_demo:
        print("[demo] Skipped (--skip-demo)")
        return

    print(f"[demo] Seeding {DEMO_APPLICATION_ID} / {DEMO_APPLICANT_ID}")
    store = EventStore(args.db_url, upcaster_registry=default_upcaster_registry())
    await store.connect()
    try:
        await seed_demo_application(store, repo_root)
        await catch_up_application_summary(store)
    finally:
        await store.close()

    print("Done. Open the UI Applications page; you should see APEX-0001 if projection ran.")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
