# Glossary

| Term | Meaning in this project |
|------|-------------------------|
| **EDA** | Events as messages between components; can be dropped; not the Ledger’s truth. |
| **Event sourcing (ES)** | Events **are** the database; full replay reconstructs state. |
| **Aggregate** | Consistency boundary; mutations produce domain events. |
| **OCC** | `expected_version` on append; conflict → reload/retry. |
| **CQRS** | Writes append events; reads query projections. |
| **Projection** | Derived read model from the event stream. |
| **Upcasting** | Migrate **read** representation of old events; storage stays immutable. |
| **Outbox** | Same-DB transactional buffer for reliable downstream publish. |
| **Gas Town** | Persist agent context/actions in the store before acting; replay for recovery. |

Extend with project-specific terms (e.g. `correlation_id`, stream prefixes) as you lock API shapes.
