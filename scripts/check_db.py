"""Quick check: list all applications in the projection + event streams."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:apex@postgres:5432/apex_ledger")
    rows = await conn.fetch(
        "SELECT application_id, state, decision FROM projection_application_summary ORDER BY updated_at DESC LIMIT 20"
    )
    print("=== Applications in projection ===")
    for r in rows:
        print(f"  {r['application_id']:20s}  state={str(r['state']):25s}  decision={r['decision']}")
    print(f"  Total: {len(rows)}")

    streams = await conn.fetch(
        "SELECT stream_id, current_version FROM event_streams WHERE stream_id LIKE 'loan-%' ORDER BY stream_id LIMIT 20"
    )
    print("\n=== Loan streams ===")
    for s in streams:
        print(f"  {s['stream_id']:30s}  v={s['current_version']}")
    await conn.close()

asyncio.run(main())
