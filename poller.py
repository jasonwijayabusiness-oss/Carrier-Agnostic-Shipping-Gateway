import time
import requests
from app.db import init_db, get_conn
from app.shipping import ingest_event

SENDLE_TRACKING_URL = "http://127.0.0.1:8000/mock/sendle/tracking"

def already_ingested(conn, tracking_number: str, event_code: str, event_time: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM tracking_events WHERE tracking_number=? AND provider='SENDLE' AND event_code=? AND event_time=? LIMIT 1",
        (tracking_number, event_code, event_time),
    ).fetchone()
    return row is not None

def main():
    init_db()
    while True:
        try:
            conn = get_conn()
            rows = conn.execute("SELECT tracking_number FROM shipments WHERE provider='SENDLE' AND label_status='SUCCESS' ORDER BY created_at DESC LIMIT 200").fetchall()
            for r in rows:
                tn = r["tracking_number"]
                resp = requests.get(f"{SENDLE_TRACKING_URL}/{tn}", timeout=5)
                if resp.status_code != 200:
                    continue
                for ev in resp.json().get("events", []):
                    event_code = (ev.get("event_code") or "").upper()
                    event_time = ev.get("event_time")
                    if event_code and event_time and not already_ingested(conn, tn, event_code, event_time):
                        ingest_event(tn, "SENDLE", event_code, event_time=event_time)
            conn.close()
        except Exception:
            pass
        time.sleep(10)

if __name__ == "__main__":
    main()
