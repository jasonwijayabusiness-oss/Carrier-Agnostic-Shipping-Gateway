from datetime import datetime, timezone
import uuid
from typing import Optional, List
from .db import get_conn

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def open_incident_if_needed(provider: str, trigger: str, notes: Optional[str] = None, opened_by: str = "system") -> str:
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT incident_id FROM incidents WHERE provider=? AND status='OPEN' ORDER BY start_time DESC LIMIT 1",
            (provider,),
        ).fetchone()
        if existing:
            return existing["incident_id"]

        incident_id = f"INC-{uuid.uuid4().hex[:10].upper()}"
        conn.execute(
            """INSERT INTO incidents(incident_id, provider, status, trigger, start_time, end_time, opened_by, closed_by, notes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (incident_id, provider, "OPEN", trigger, now_iso(), None, opened_by, None, notes),
        )
        conn.commit()
        return incident_id
    finally:
        conn.close()

def list_incidents(limit: int = 200) -> List[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM incidents ORDER BY start_time DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
