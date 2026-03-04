from datetime import datetime, timezone
import json
import uuid
from typing import Tuple
from .db import get_conn

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def run_release_gate() -> Tuple[str, dict]:
    conn = get_conn()
    run_id = f"RUN-{uuid.uuid4().hex[:10].upper()}"
    started_at = now_iso()
    results = []
    status = "PASS"
    try:
        checks = conn.execute("SELECT check_name, severity, description, sql_fail_count FROM release_checks WHERE enabled=1 ORDER BY check_id ASC").fetchall()
        for c in checks:
            row = conn.execute(c["sql_fail_count"]).fetchone()
            fail_cnt = int(row["fail_cnt"]) if row and row["fail_cnt"] is not None else 0
            passed = (fail_cnt == 0)
            if c["severity"].upper() == "BLOCKER" and not passed:
                status = "FAIL"
            results.append({"check_name": c["check_name"], "severity": c["severity"], "description": c["description"], "fail_cnt": fail_cnt, "passed": passed})
        finished_at = now_iso()
        conn.execute("INSERT INTO release_runs(run_id, started_at, finished_at, status, results_json) VALUES (?,?,?,?,?)",
                     (run_id, started_at, finished_at, status, json.dumps(results)))
        conn.commit()
        return run_id, {"run_id": run_id, "started_at": started_at, "finished_at": finished_at, "status": status, "results": results}
    finally:
        conn.close()
