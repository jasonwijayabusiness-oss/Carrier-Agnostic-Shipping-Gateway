import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(os.getenv("DB_PATH", "data/app.db"))

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS provider_status (
  provider TEXT PRIMARY KEY,
  is_enabled INTEGER NOT NULL,
  last_error TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  seller_postcode TEXT NOT NULL,
  buyer_postcode TEXT NOT NULL,
  weight_kg REAL NOT NULL,
  length_cm REAL NOT NULL,
  width_cm REAL NOT NULL,
  height_cm REAL NOT NULL,
  collection_method TEXT NOT NULL, -- PICKUP / DROPOFF / PRINTER_FREE
  promised_days INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shipments (
  shipment_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  label_status TEXT NOT NULL,
  label_url TEXT,
  tracking_number TEXT,
  estimated_cost REAL,
  estimated_days INTEGER,
  selection_reason TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS label_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  success INTEGER NOT NULL,
  error_code TEXT,
  error_message TEXT,
  latency_ms INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracking_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tracking_number TEXT NOT NULL,
  provider TEXT NOT NULL,
  event_code TEXT NOT NULL,
  canonical_status TEXT NOT NULL,
  event_time TEXT NOT NULL,
  received_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS carriers (
  provider TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL,
  base_price REAL NOT NULL,
  price_per_kg REAL NOT NULL,
  pickup_fee REAL NOT NULL,
  metro_sla_days INTEGER NOT NULL,
  regional_sla_days INTEGER NOT NULL,
  supports_pickup INTEGER NOT NULL,
  supports_dropoff INTEGER NOT NULL,
  supports_printer_free INTEGER NOT NULL,
  max_weight_kg REAL NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  lane_type TEXT NOT NULL,
  quoted_cost REAL,
  estimated_days INTEGER,
  eligible INTEGER NOT NULL,
  ineligible_reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
  incident_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT,
  opened_by TEXT NOT NULL,
  closed_by TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS release_checks (
  check_id INTEGER PRIMARY KEY AUTOINCREMENT,
  check_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  severity TEXT NOT NULL DEFAULT 'BLOCKER',
  description TEXT,
  sql_fail_count TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS release_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  results_json TEXT
);
"""

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def seed_defaults(conn: sqlite3.Connection) -> None:
    for provider in ("SENDLE", "ALT", "AUSPOST"):
        row = conn.execute("SELECT provider FROM provider_status WHERE provider=?", (provider,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO provider_status(provider, is_enabled, last_error, updated_at) VALUES (?,?,?,?)",
                (provider, 1, None, now_iso()),
            )

    # SIMULATION numbers (not real pricing)
    carriers = [
        ("SENDLE", 1, 7.00, 1.20, 2.00, 2, 5, 1, 1, 1, 25.0),  # pickup+dropoff+printer-free
        ("ALT",    1, 6.50, 1.40, 3.00, 2, 4, 1, 1, 0, 30.0),  # pickup+dropoff
        ("AUSPOST",1, 8.00, 1.10, 0.00, 1, 3, 0, 1, 0, 22.0),  # dropoff only, faster metro
    ]
    for c in carriers:
        row = conn.execute("SELECT provider FROM carriers WHERE provider=?", (c[0],)).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO carriers(provider, enabled, base_price, price_per_kg, pickup_fee,
                                           metro_sla_days, regional_sla_days,
                                           supports_pickup, supports_dropoff, supports_printer_free,
                                           max_weight_kg, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*c, now_iso()),
            )

    cnt = conn.execute("SELECT COUNT(*) AS c FROM release_checks").fetchone()["c"]
    if not cnt:
        checks = [
            (
                "Carrier label failures last 10m should be low (BLOCKER if >=3)",
                "BLOCKER",
                "Counts failed label attempts across all providers in last 10 minutes. If >=3, stop rollout.",
                """SELECT CASE WHEN COUNT(*) >= 3 THEN COUNT(*) ELSE 0 END AS fail_cnt
                   FROM label_attempts
                   WHERE success=0 AND created_at >= datetime('now','-10 minutes');""",
            ),
            (
                "Orders with NO eligible carrier should be 0 (WARN)",
                "WARN",
                "Counts orders for which latest quotes show zero eligible carriers.",
                """WITH latest_quotes AS (
                     SELECT rq.*
                     FROM rate_quotes rq
                     JOIN (
                       SELECT order_id, provider, MAX(created_at) AS mx
                       FROM rate_quotes
                       GROUP BY order_id, provider
                     ) x ON rq.order_id=x.order_id AND rq.provider=x.provider AND rq.created_at=x.mx
                   ),
                   by_order AS (
                     SELECT order_id, SUM(CASE WHEN eligible=1 THEN 1 ELSE 0 END) AS elig_cnt
                     FROM latest_quotes
                     GROUP BY order_id
                   )
                   SELECT COUNT(*) AS fail_cnt
                   FROM by_order
                   WHERE elig_cnt=0;""",
            ),
        ]
        for name, severity, desc, sql in checks:
            conn.execute(
                """INSERT INTO release_checks(check_name, enabled, severity, description, sql_fail_count, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (name, 1, severity, desc, sql, now_iso()),
            )

def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA_SQL)
        seed_defaults(conn)
        conn.commit()
    finally:
        conn.close()
