# Alert Enrichments (Planned)

This document outlines potential backend enrichments to improve prioritization and explainability of alerts. Implementations are not yet applied; they describe the intended changes for next iterations.

## 1) GDS Risk Scoring
- **Goal:** Add graph-derived risk scores (e.g., PageRank/Betweenness) on `TRANSACTED_WITH` or identifier-sharing networks.
- **Usage:** Include `riskScoreGds` in alert payloads (R1/R3/R7) and use it for severity/prioritization.
- **Changes:** Add a GDS query in the `fetch_*` functions or precompute and cache scores; return `riskScoreGds`.

## 2) Community Detection for Mule Rings
- **Goal:** Use GDS Louvain/Connected Components on `TRANSACTED_WITH` or shared identifiers to detect clusters.
- **Usage:** Add `communityId`/`communitySize` to R3/R7 payloads; surface ring size more meaningfully.
- **Changes:** Add a GDS call for communities; attach cluster metadata to alerts.

## 3) Temporal Velocity Flags
- **Goal:** Flag high transaction velocity in a recent window (e.g., last 24–48h).
- **Usage:** Add `txLast24h`, `burstFlag` to R1/R7 responses; use in severity/priority.
- **Changes:** Extend `fetch_*` queries with a sliding-window count; return counts/flags.

## 4) Identifier Anomaly/Risk Ratio
- **Goal:** Flag identifiers with abnormal sharing (e.g., high risky/total ratio).
- **Usage:** In R2, include `riskRatio = riskyAccounts / totalAccounts` and `anomaly` boolean; sort by ratio.
- **Changes:** Compute ratio in R2; add fields to payload; adjust severity mapping if desired.

## 5) Rule Metadata and Evidence
- **Goal:** Provide concise “why”/evidence strings for each alert.
- **Usage:** Add `evidence` (e.g., top contributors, risky neighbor count) to alert payloads.
- **Changes:** Build evidence strings in each `fetch_*` function and include them in API responses.

## 6) Composite Priority
- **Goal:** Provide a single `priorityScore` combining severity + GDS risk + velocity/anomaly flags.
- **Usage:** Sort alerts server-side by `priorityScore`; expose it in payloads.
- **Changes:** Compute a simple composite per alert and sort before returning.

## Notes
- These enrichments are additive and optional; they do not remove existing fields.
- Minimal UI changes: expose new fields in summaries/columns and/or use them for sorting.
- Graphviz/graph rendering changes are not required; these are data-level enrichments.
