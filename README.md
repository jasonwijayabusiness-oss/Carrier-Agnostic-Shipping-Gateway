# Carrier-Agnostic Shipping Gateway (Sendle Shutdown Simulator)

A lightweight end-to-end demo of how an eBay-like marketplace can remain resilient when a shipping provider or aggregator (for example Sendle) becomes unavailable.

This project simulates:
- Rate shopping across multiple carriers (cost + SLA)
- Capability-aware routing (pickup vs drop-off vs printer-free)
- Promise-aware routing (choose a carrier that meets the delivery promise when possible)
- Label creation via carrier APIs (mocked)
- Provider kill switch + failover when Sendle goes down
- SQL-first observability (quotes, label attempts, incidents, release gates)
- A simple Streamlit dashboard for operational visibility

Note: pricing, SLAs, and lane logic are simulated for demonstration only.

---

## Why this exists

Marketplaces often depend on third-party shipping providers for core workflows like label purchase and tracking events. If a provider becomes unavailable, sellers can lose label options and the marketplace can see higher support contacts, more disputes, and lower trust.

This prototype represents an internal carrier-agnostic shipping layer that:
- isolates the marketplace from single-provider dependency
- introduces redundancy and controlled routing
- provides operational tooling for monitoring health and investigating incidents using SQL

---

## High-level architecture

Marketplace (eBay-like)
→ calls Shipping Gateway API (FastAPI)
→ gateway reads SQLite for carrier config + constraints
→ gateway rate-shops and selects best carrier
→ gateway calls mock carrier label APIs (Sendle, ALT, AusPost)
→ gateway writes quotes, label attempts, shipments, incidents into SQLite
→ Streamlit dashboard reads SQLite for operational visibility
→ optional poller simulates polling-based tracking ingestion

---

## Tech stack

- Python
- FastAPI + Uvicorn
- SQLite (free file-based database)
- Streamlit
- Pandas + Matplotlib

---

## Repo layout

- app/
  - main.py              FastAPI service
  - db.py                SQLite schema + seeding
  - quotes.py             rate shopping + eligibility + promise routing logic
  - shipping.py           label creation + failover + kill switch + incident open
  - incidents.py          incident helpers
  - release_gate.py       SQL-driven release checks and runs
  - mocks/                mock carrier APIs
- dashboard.py            Streamlit ops dashboard
- poller.py               optional polling-based tracking ingestion simulator
- sql/                    example SQL queries for audits and investigations
- scripts/                helper scripts (batch demo, reset)

---

## Setup (local)

### 1) Create and activate a virtual environment (recommended)

Windows PowerShell:
```powershell```
python -m venv .venv
.venv\Scripts\Activate.ps1

Mac/Linux:
python -m venv .venv
source .venv/bin/activate

### 2) Install dependencies
python -m pip install -r requirements.txt

### 3) Run the demo (3 terminals)

Terminal 1 (API):
python -m uvicorn app.main:app --reload --port 8000

```API docs: http://127.0.0.1:8000/docs```

Terminal 2 (poller, optional):
python poller.py

Terminal 3 (Dashboard):
python -m streamlit run dashboard.py
```Streamlit typically: http://localhost:8501 ```
