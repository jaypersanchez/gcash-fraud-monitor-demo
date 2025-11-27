# GCash Fraud Monitor Demo (POC)

Click-through proof-of-concept for a GCash-style fraud monitoring workflow. Backend uses Flask + PostgreSQL with mock Neo4j detections; frontend is a minimal JavaScript SPA (no bundler) with a GCash-inspired UI.

## Prerequisites
- Python 3.x
- PostgreSQL running locally (create a database, e.g., `gcash_fraud_demo`)
- Node 18+

## Backend Setup
1) `cd backend`
2) Create and activate a virtualenv.
3) Copy `.env.example` to `.env` (defaults to `postgres/postgres@localhost:5432/gcash_fraud_demo`); adjust if your DB differs.
4) Install deps: `pip install -r requirements.txt`
5) Start API: `python app.py` (runs on port 5000 by default)

Notes:
- On startup, tables are created and seed data is inserted (rules, accounts, devices).
- API base: `http://localhost:5000/api`

## Frontend Setup (no build tools)
1) `cd frontend`
2) Serve the static files (choose one):
   - `python -m http.server 8000`
   - or any simple static server
3) Open `http://localhost:8000` (or the server port you used). The frontend calls the backend at `http://localhost:5000/api`.

## Demo Flow
1) Start backend and frontend.
2) Open the app (Vite dev URL).
3) Alerts page:
   - Click **Refresh Alerts** (POST `/api/alerts/refresh`) to generate mock alerts.
   - View sorted alert list (severity/time). Click any alert row.
4) Case page:
   - Review alert header and subject account.
   - Read network summary, linked accounts/devices.
   - Take actions (Block, Mark Safe, Escalate) → POST `/api/cases/:id/actions`; status updates and audit trail grows.
   - Audit trail shows chronological actions.
   - Graph View placeholder notes future Neo4j/Bloom integration.

## Key API Endpoints
- `GET /api/health`
- `GET /api/rules`, `GET /api/rules/:id`
- `POST /api/alerts/refresh` (mock detections → alerts + cases)
- `GET /api/alerts` (filters by `status`), `GET /api/alerts/:id`
- `POST /api/cases/:id/actions`, `GET /api/cases/:id/audit`

## Testing
- Ensure `DATABASE_URL` points to a test-safe Postgres database.
- From `backend`: `pytest`
