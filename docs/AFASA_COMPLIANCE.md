# AFASA Compliance Simulation

This demo models the Anti-Financial Account Scamming Act (RA 12010) and BSP Circulars 1213–1215 inside the fraud monitoring pipeline. It is not a core-banking implementation; it is a compliance-aware facade to illustrate how a BSI could operationalize AFASA controls.

## Concepts covered
- **Money mule, social engineering, economic sabotage** heuristics with AFASA rule helpers (`backend/afasa/rules.py`).
- **Disputed transactions** with temporary holds, verification timeline, and max-hold enforcement (`AfasaDisputedTransaction`, `AfasaVerificationEvent`).
- **BSP 1213 logging** via `TransactionLog`, capturing sender/receiver, channel, auth method, device fingerprint, IP/UA, and network reference.
- **Case-ready bundles** via reporting endpoints and graph export hooks for BSP/AMLC/LEA sharing.

## Flow (modeled)
1. Suspicious transaction or FAF alert triggers AFASA risk evaluation (`evaluate_afasa_risk`).
2. Alerts are tagged as AFASA with suspicion type + risk score; optional dispute auto-creation.
3. Analyst (or Telegram bot) can create a dispute and apply a temporary hold (simulated), automatically bounded by 30 days.
4. Verification events log customer and other-BFI coordination; all actions are time-stamped.
5. Final decision releases or restitutes funds; events form the audit trail for BSP/CAPO.

## Data model highlights
- `TransactionLog` (`backend/models/transaction.py`): BSP 1213-aligned log row for every simulated transaction, including auth + device metadata.
- `AfasaDisputedTransaction`: links alert + transaction, captures hold window, suspicion, and status transitions.
- `AfasaVerificationEvent`: immutable timeline of verification steps (customer contact, other BFI, BSP query, release/restitution).
- `AfasaMoneyMuleFlag`: track flagged accounts and confidence with source provenance.

## API surface (see `backend/routes/afasa.py`)
- `POST /api/afasa/disputes` – create dispute from alert/tx.
- `POST /api/afasa/disputes/{id}/hold` – apply temporary hold (starts 30-day clock).
- `POST /api/afasa/disputes/{id}/release` – release or restitute.
- `POST /api/afasa/disputes/{id}/events` – add verification timeline entries.
- `GET /api/afasa/disputes` / `GET /api/afasa/disputes/{id}` – list/detail with events.
- `GET /api/afasa/reports/summary` – volumes by status/suspicion; avg hold can be added.
- `GET /api/afasa/reports/case/{id}` – dispute bundle + alert metadata for sharing.

## AFASA rule helpers (demo heuristics)
- **Money mule**: fan-in count, pass-through ratio, high-value flagging.
- **Social engineering**: weak auth (OTP SMS), device change near transfer, behavioral spike.
- **Economic sabotage**: hook for batch cluster detection (extend against Neo4j).
- Aggregated risk drives recommended actions: `TEMP_HOLD_AND_VERIFY`, `MONITOR_ONLY`, `NO_ACTION`.

## Disputed transaction lifecycle
1. `PENDING_HOLD` (created) → `HELD` (hold applied, 30-day max window set).
2. Verification events log customer/other-BFI/BSP contacts.
3. Decision: `RELEASED`, `WRITTEN_OFF` (restitution), or `ESCALATED` (LEA).
4. Background guard (`auto_enforce_max_hold_period`) escalates holds that exceed max hold.

## Graph + chain view
When a dispute is created, the transaction reference can be tied to Neo4j transfers so a “dispute chain” can be visualized (see `neo4j_client_mock` hooks and `TransactionLog` linkage). Extend with the `/afasa/disputes/{id}/graph` endpoint to pull multi-hop chains for BSP visibility.

## Diagram
See `docs/afasa_flow.puml` and generated `docs/afasa_flow.png` for the end-to-end sequence across Customer, GCash core (simulated), Fraud Monitoring, Other BFI, and BSP/CAPO.
