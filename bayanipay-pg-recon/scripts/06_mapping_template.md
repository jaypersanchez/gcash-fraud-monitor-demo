# Neo4j Mapping Draft (Template)

Use this after collecting schema metadata. Fill in per database.

## Candidate node labels
- Account / Wallet / Customer
- Merchant / Beneficiary
- Device / Identifier (email/phone/SSN/IP/device fingerprint)
- Transaction / Transfer / Payment / Payout
- Alert / Case / Dispute / RiskEvent

## Source tables per node
| Node Label | Source Table(s) | Key Column(s) | Important Properties | Notes |
|------------|-----------------|---------------|----------------------|-------|
| Account    |                 |               | status, created_at   |       |
| Merchant   |                 |               | category, risk_level |       |
| Device     |                 |               | type, fingerprint    |       |
| Identifier |                 |               | email/phone/ip       |       |
| Transaction|                 |               | amount, currency, ts |       |
| Alert      |                 |               | rule_key, severity   |       |
| Case       |                 |               | status, owner, sla   |       |

## Candidate relationships
- Account -> Transaction: `(:Account)-[:INITIATED]->(:Transaction)`
- Transaction -> Account: `(:Transaction)-[:TO]->(:Account)` (receiver)
- Account -> Merchant: `(:Account)-[:PAYS]->(:Merchant)`
- Account -> Device: `(:Account)-[:USES_DEVICE]->(:Device)`
- Account -> Identifier: `(:Account)-[:HAS_IDENTIFIER]->(:Identifier)`
- Alert -> Account: `(:Alert)-[:ALERTS_ON]->(:Account)`
- Case -> Alert: `(:Case)-[:COVERS]->(:Alert)`

Specify join logic for each (FKs or inferred links).

## Key properties per node/edge
- Normalize timestamps (UTC), amounts (decimal + currency), enums/status values.
- Include provenance: source table/column, load timestamp.

## Ambiguities / open questions
- Which tables hold canonical customer vs merchant data?
- Are device identifiers consistent (IMEI/IMSI/fingerprint)?
- Do alerts map to cases 1:1 or 1:many?
- How to treat soft-deletes / historical tables?

## TODOs
- Confirm primary keys and stable identifiers for each node type.
- Validate any denormalized transaction views vs raw ledgers.
- Decide on de-duplication rules for identifiers (email/phone/device).
