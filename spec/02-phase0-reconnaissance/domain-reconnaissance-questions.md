# DOMAIN_NOTES — six questions

Answer in **`DOMAIN_NOTES.md`** before large implementation. Source: [`../../ref_docs/requirements.md`](../../ref_docs/requirements.md).

1. **EDA vs ES** — A component uses callbacks (e.g. LangChain-style traces) to capture event-like data. Is that EDA or ES? If you redesigned it to use the Ledger, what exactly would change and what would you gain?

2. **Aggregate boundary** — You will implement four aggregates. Name **one alternative boundary** you considered and rejected. What **coupling problem** does your chosen boundary prevent?

3. **Concurrency** — Two agents both call append with `expected_version=3` on the same stream. Trace the **exact sequence** in the event store. What does the **loser** receive, and what must it do next?

4. **Projection lag** — LoanApplication read model lags ~200ms. A loan officer queries “available credit limit” immediately after a disbursement event is appended; they see the **old** value. What does the system do, and how does the **UI** communicate eventual consistency?

5. **Upcasting** — `CreditDecisionMade` was `{application_id, decision, reason}`; it must become `{..., model_version, confidence_score, regulatory_basis}`. Sketch the **upcaster**. What is your **inference strategy** for historical events that predate `model_version`?

6. **Distributed projections** — Marten-style multi-node projection runners. How would you achieve similar behaviour in Python? What **coordination primitive** (lease, advisory lock, DB row, etc.) and what **failure mode** does it prevent?
