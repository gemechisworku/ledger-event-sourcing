# Regulatory examination package

**Source:** [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md) — Phase 6.

## `generate_regulatory_package(application_id, examination_date)`

Self-contained **JSON** export:

1. Complete event stream for the application, ordered, full payloads.
2. State of **every projection** at `examination_date`.
3. Audit chain integrity verification result.
4. Human-readable narrative — one sentence per significant event (generated from replay).
5. Per-agent: model versions, confidence scores, input data hashes.

**Independence:** A regulator can verify the JSON against the live DB **without** trusting only your app’s word — structure must be reproducible.
