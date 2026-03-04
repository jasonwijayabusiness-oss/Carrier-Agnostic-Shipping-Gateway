from fastapi import FastAPI, HTTPException
from datetime import datetime, timezone
import random

from .db import init_db, get_conn
from .mocks.sendle import router as sendle_router
from .mocks.alt import router as alt_router
from .mocks.auspost import router as auspost_router
from .shipping import create_label_best, ingest_event, set_provider_enabled
from .quotes import generate_quotes
from .incidents import list_incidents
from .release_gate import run_release_gate
from .models import SeedOrdersRequest, CreateLabelRequest, PushEventRequest, TrackingResponse, TrackingEvent

app = FastAPI(title="Carrier-Agnostic Shipping Platform (V3)", version="3.0.0")

@app.on_event("startup")
def startup():
    init_db()

app.include_router(sendle_router)
app.include_router(alt_router)
app.include_router(auspost_router)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def rand_postcode() -> str:
    return str(random.randint(2000, 3999))

def rand_dims():
    return (round(random.uniform(10, 40), 1), round(random.uniform(10, 30), 1), round(random.uniform(2, 20), 1))

@app.post("/orders/seed")
def seed_orders(req: SeedOrdersRequest):
    conn = get_conn()
    created = []
    try:
        for i in range(req.n):
            order_id = f"ORDER-{i+1:04d}"
            weight = round(random.uniform(0.2, 18.0), 2)
            l, w, h = rand_dims()
            method = random.choice(["PICKUP", "DROPOFF", "PRINTER_FREE"])
            promised = random.choice([2, 3, 4, 5])
            conn.execute(
                """INSERT OR IGNORE INTO orders(order_id, seller_postcode, buyer_postcode, weight_kg, length_cm, width_cm, height_cm,
                                                  collection_method, promised_days, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (order_id, rand_postcode(), rand_postcode(), weight, l, w, h, method, promised, now_iso()),
            )
            created.append(order_id)
        conn.commit()
        return {"seeded": len(created), "order_ids": created}
    finally:
        conn.close()

@app.get("/orders")
def list_orders(limit: int = 200):
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {"orders": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.get("/carriers")
def list_carriers():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM carriers ORDER BY provider").fetchall()
        return {"carriers": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.post("/carriers/{provider}/toggle")
def toggle_carrier(provider: str, enabled: bool = True):
    conn = get_conn()
    try:
        conn.execute("UPDATE carriers SET enabled=?, updated_at=? WHERE provider=?", (1 if enabled else 0, now_iso(), provider))
        conn.commit()
        return {"provider": provider, "enabled": enabled}
    finally:
        conn.close()

@app.get("/providers")
def providers():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM provider_status ORDER BY provider").fetchall()
        return {"providers": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.post("/providers/{provider}/enable")
def enable_provider(provider: str):
    set_provider_enabled(provider, True, last_error=None)
    return {"provider": provider, "enabled": True}

@app.post("/providers/{provider}/disable")
def disable_provider(provider: str):
    set_provider_enabled(provider, False, last_error="manual_disable")
    return {"provider": provider, "enabled": False}

@app.get("/quotes/{order_id}")
def quotes(order_id: str):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")
        order = dict(row)
    finally:
        conn.close()
    q = generate_quotes(order)
    return {"order_id": order_id, "quotes": q}

@app.get("/quotes")
def list_quotes(limit: int = 200):
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM rate_quotes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {"quotes": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.post("/shipments/create_label")
def create_label(req: CreateLabelRequest):
    return create_label_best(req.order_id)

@app.get("/shipments")
def list_shipments(limit: int = 200):
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM shipments ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {"shipments": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.post("/webhooks/tracking/{provider}")
def tracking_webhook(provider: str, req: PushEventRequest):
    event_time = req.event_time or now_iso()
    ingest_event(req.tracking_number, provider.upper(), req.event_code, event_time=event_time)
    return {"ok": True}

@app.get("/tracking/{tracking_number}", response_model=TrackingResponse)
def get_tracking(tracking_number: str):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT provider, event_code, canonical_status, event_time, received_time FROM tracking_events WHERE tracking_number=? ORDER BY event_time ASC, id ASC",
            (tracking_number,),
        ).fetchall()
        events = [TrackingEvent(provider=r["provider"], event_code=r["event_code"], canonical_status=r["canonical_status"], event_time=r["event_time"], received_time=r["received_time"]) for r in rows]
        return TrackingResponse(tracking_number=tracking_number, events=events)
    finally:
        conn.close()

@app.get("/incidents")
def incidents(limit: int = 200):
    return {"incidents": list_incidents(limit=limit)}

@app.post("/ops/release_gate_run")
def release_gate_run():
    _, payload = run_release_gate()
    return payload
