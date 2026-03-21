# Cryptographic audit chain

- Stream: `audit-{entity_type}-{entity_id}`.
- `run_integrity_check` computes chained hash over events since last check; appends `AuditIntegrityCheckRun`.
- Return: counts, `chain_valid`, `tamper_detected`.
