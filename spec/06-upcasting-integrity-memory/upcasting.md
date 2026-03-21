# Upcasting

- **On load:** apply registry transparently; callers never invoke upcasters manually.
- **Immutability:** raw DB row unchanged — cover with a dedicated test.
- **Examples:** `CreditAnalysisCompleted` v1→v2, `DecisionGenerated` v1→v2 (may require store lookup — document cost).
