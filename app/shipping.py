from datetime import datetime, timezone
import time
import uuid
from typing import Optional, Tuple
import requests

from .db import get_conn
from .normalization import canonicalize
from .quotes import generate_quotes, choose_best_provider
from .incidents import open_incident_if_needed

SENDLE_LABEL_URL = "http://127.0.0.1:8000/mock/sendle/labels"
ALT_LABEL_URL = "http://127.0.0.1:8000/mock/alt/labels"
AUSPOST_LABEL_URL = "http://127.0.0.1:8000/mock/auspost/labels"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ms_since(t0: float) -> int:
    return int((time.time() - t0) * 1000)

def get_order(order_id: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not row:
            raise KeyError("Order not found")
        return dict(row)
    finally:
        conn.close()

def get_provider_enabled(provider: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute("SELECT is_enabled FROM provider_status WHERE provider=?", (provider,)).fetchone()
        return bool(row["is_enabled"]) if row else False
    finally:
        conn.close()

def set_provider_enabled(provider: str, enabled: bool, last_error: Optional[str] = None) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE provider_status SET is_enabled=?, last_error=?, updated_at=? WHERE provider=?",
            (1 if enabled else 0, last_error, now_iso(), provider),
        )
        conn.commit()
    finally:
        conn.close()

def insert_label_attempt(order_id: str, provider: str, success: bool, error_code: Optional[str], error_message: Optional[str], latency_ms: Optional[int]) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO label_attempts(order_id, provider, success, error_code, error_message, latency_ms, created_at) VALUES (?,?,?,?,?,?,?)",
            (order_id, provider, 1 if success else 0, error_code, error_message, latency_ms, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()

def create_shipment_record(order_id: str, provider: str, label_status: str, label_url: Optional[str], tracking_number: Optional[str],
                           estimated_cost: Optional[float], estimated_days: Optional[int], selection_reason: Optional[str]) -> dict:
    shipment_id = f"SHP-{uuid.uuid4().hex[:10].upper()}"
    created_at = now_iso()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO shipments(shipment_id, order_id, provider, label_status, label_url, tracking_number,
                                       estimated_cost, estimated_days, selection_reason, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (shipment_id, order_id, provider, label_status, label_url, tracking_number, estimated_cost, estimated_days, selection_reason, created_at),
        )
        conn.commit()
    finally:
        conn.close()
    return {"shipment_id": shipment_id, "order_id": order_id, "provider": provider, "label_status": label_status,
            "label_url": label_url, "tracking_number": tracking_number, "estimated_cost": estimated_cost, "estimated_days": estimated_days,
            "selection_reason": selection_reason, "created_at": created_at}

def ingest_event(tracking_number: str, provider: str, event_code: str, event_time: str, received_time: Optional[str] = None) -> None:
    received_time = received_time or now_iso()
    canonical = canonicalize(provider, event_code)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO tracking_events(tracking_number, provider, event_code, canonical_status, event_time, received_time) VALUES (?,?,?,?,?,?)",
            (tracking_number, provider, event_code.upper(), canonical, event_time, received_time),
        )
        conn.commit()
    finally:
        conn.close()

def label_api(provider: str) -> str:
    if provider == "SENDLE":
        return SENDLE_LABEL_URL
    if provider == "ALT":
        return ALT_LABEL_URL
    return AUSPOST_LABEL_URL

def call_label_api(url: str, payload: dict, timeout: float = 4.0) -> Tuple[bool, dict, Optional[str], Optional[str]]:
    t0 = time.time()
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        latency = ms_since(t0)
        if r.status_code >= 400:
            return False, {"latency_ms": latency}, str(r.status_code), r.text
        data = r.json()
        data["latency_ms"] = latency
        return True, data, None, None
    except requests.Timeout:
        latency = ms_since(t0)
        return False, {"latency_ms": latency}, "408", "timeout"
    except Exception as e:
        latency = ms_since(t0)
        return False, {"latency_ms": latency}, "500", str(e)

def create_label_best(order_id: str) -> dict:
    order = get_order(order_id)
    quotes = generate_quotes(order)
    chosen, meta = choose_best_provider(order, quotes)
    selection_reason = meta.get("selection_reason")

    eligible = [q for q in quotes if q["eligible"] == 1]
    if not eligible:
        return create_shipment_record(order_id, "AUSPOST", "FAILED", None, None, None, None, selection_reason)

    promised = int(order["promised_days"])
    meets = sorted([q for q in eligible if int(q["estimated_days"]) <= promised], key=lambda x: (float(x["quoted_cost"]), int(x["estimated_days"])))
    rest = sorted([q for q in eligible if int(q["estimated_days"]) > promised], key=lambda x: (int(x["estimated_days"]), float(x["quoted_cost"])))
    ranked = meets + rest
    ranked = sorted(ranked, key=lambda q: 0 if q["provider"] == chosen else 1)

    last_err = None
    for q in ranked:
        prov = q["provider"]
        if not get_provider_enabled(prov):
            continue

        ok, out, err_code, err_msg = call_label_api(label_api(prov), order)
        insert_label_attempt(order_id, prov, ok, err_code, err_msg, out.get("latency_ms"))

        if ok:
            tn = out["tracking_number"]
            lbl = out["label_url"]
            ingest_event(tn, prov, "LABEL_CREATED", event_time=now_iso())
            return create_shipment_record(order_id, prov, "SUCCESS", lbl, tn, q["quoted_cost"], q["estimated_days"], selection_reason)

        last_err = f"{err_code}:{err_msg}"
        if prov == "SENDLE":
            set_provider_enabled("SENDLE", False, last_error=last_err)
            open_incident_if_needed("SENDLE", trigger="LABEL_API_FAILURE_KILL_SWITCH", notes=last_err)

    return create_shipment_record(order_id, chosen, "FAILED", None, None, None, None, f"{selection_reason}|ALL_FAILED:{last_err}")
