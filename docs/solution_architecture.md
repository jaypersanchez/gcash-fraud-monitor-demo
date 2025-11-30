# Solution Architecture (High-Level)

## 1. Objective
A demo-ready fraud monitoring system for a GCash-style wallet:
- Detect risky accounts/identifiers via Neo4j rules (R1/R2/R3/R7 + Search & Destroy).
- Investigate via interactive graph drill-down and case actions.
- Push alerts/assessments to Telegram; optional AI risk assessment (OpenAI).
- Foundation for adding live/streaming monitoring.

## 2. Core Components
- **Frontend (vanilla JS/Cytoscape)**: Alerts list, filters, graph view (account vs identifier), actions/notes, Search & Destroy mode, flagging, and selection drill-down.
- **Backend (Flask)**:
  - API for alerts (R1/R2/R3/R7/Search & Destroy).
  - Graph endpoints (account/identifier) returning nodes/edges with flags/subjects.
  - Investigator actions/notes in Postgres.
  - AI assess endpoint (graph → PNG via Graphviz; OpenAI gpt-4o summary).
  - Health checks.
- **Neo4j**: Graph store for accounts/mules/identifiers/transactions; rules executed via Cypher.
- **Postgres**: Investigator flags/notes (persistence independent of Neo4j).
- **Telegram agent**: Polls top unflagged suspects, triggers AI assess, and sends assessment + PNG to chat.

## 3. Data Flow (Current)
1) User selects a rule or Search & Destroy → backend fetches alerts from Neo4j (filters flagged for R1/R3/R7; unflagged for S&D by toggle).
2) User clicks an alert → graph endpoint loads context (anchor account or identifier) → Cytoscape renders with subject/flagged highlighting.
3) User actions: flag (persists in Postgres), notes/actions (Postgres), case status update (Postgres).
4) AI Assess (optional): POST `/api/ai-agent/assess` → build graph, render PNG, call OpenAI → return assessment.
5) Telegram agent: polls `/api/ai-agent/top`, posts alerts, triggers `/assess`, sends text + PNG to chat.

## 4. Deployment / Config
- `.env` (gitignored): Neo4j URI/creds, Postgres URL, Telegram bot token/chat id, OpenAI key, agent intervals.
- Dependencies: Flask, SQLAlchemy, Neo4j driver, Cytoscape (frontend), Graphviz (`dot`) for PNGs, OpenAI (optional).
- Ports: backend default 5005; frontend served statically (e.g., 8000); Telegram agent runs as a separate process (polling).

## 5. Proposed Live Monitoring (Next)
- **Ingestion**: accept streaming transactions (Kafka/webhook) and upsert into Neo4j/side cache.
- **Incremental rules**: on each transaction, evaluate:
  - Fan-in/Fan-out counts (R7/R1 variants), shared identifiers (R2), velocity windows (tx in last X minutes).
- **Risk scoring**: maintain short-term aggregates (Redis/Neo4j), periodically run GDS centrality/community for risk ranking.
- **Real-time alerts**: emit/push when thresholds hit; optional auto-flag/block hooks; feed into Telegram/UI live view.

## 6. Future Enrichments (Planned)
- GDS risk scores (PageRank/Betweenness) and community detection in alerts.
- Temporal velocity/burst flags; identifier anomaly ratios.
- Evidence strings per alert; composite `priorityScore`.
- Additional rules (triangulation, layering, circularity) and configurable Cypher templates.

## 7. Security/Notes (Demo)
- Secrets in `.env`; do not commit tokens/keys.
- LibreSSL warning is benign; for production use OpenSSL-backed Python.
- Graphviz required for PNG rendering; graceful degradation if absent.
