# Phase → tests

| Phase | Command |
|-------|---------|
| 0 | `uv run pytest tests/test_schema_and_generator.py -v` |
| 1 | `uv run pytest tests/test_event_store.py -v` |
| 2 | `uv run pytest tests/test_domain.py -v` |
| 3 | `uv run pytest tests/test_narratives.py -v` |
| 4 | `uv run pytest tests/test_projections.py -v` |
| 5 | `uv run pytest tests/test_mcp.py -v` |

Some files appear as the project grows; see `tests/phase1/` if present.
