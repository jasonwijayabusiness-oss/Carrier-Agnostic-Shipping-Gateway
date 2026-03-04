from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import random
from typing import Dict, List

router = APIRouter(prefix="/mock/sendle", tags=["mock_sendle"])
SENDLE_SHUTDOWN = {"enabled": False}
SENDLE_TRACKING: Dict[str, List[dict]] = {}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@router.post("/toggle_shutdown")
def toggle_shutdown(payload: dict):
    shutdown = bool(payload.get("shutdown", False))
    SENDLE_SHUTDOWN["enabled"] = shutdown
    return {"provider": "SENDLE", "shutdown": shutdown}

@router.post("/labels")
def create_label(payload: dict):
    if SENDLE_SHUTDOWN["enabled"]:
        raise HTTPException(status_code=503, detail="Sendle service unavailable (simulated shutdown)")
    tracking = f"SENDLE-TRACK-{random.randint(100000, 999999)}"
    label_url = f"https://labels.sendle.mock/{tracking}.pdf"
    SENDLE_TRACKING.setdefault(tracking, [])
    SENDLE_TRACKING[tracking].append({"event_code": "LABEL_CREATED", "event_time": now_iso()})
    return {"tracking_number": tracking, "label_url": label_url}

@router.get("/tracking/{tracking_number}")
def get_tracking(tracking_number: str):
    return {"tracking_number": tracking_number, "events": SENDLE_TRACKING.get(tracking_number, [])}

@router.post("/add_event")
def add_event(payload: dict):
    tracking = payload.get("tracking_number")
    if not tracking:
        raise HTTPException(status_code=400, detail="tracking_number required")
    event_code = (payload.get("event_code") or "").upper()
    event_time = payload.get("event_time") or now_iso()
    SENDLE_TRACKING.setdefault(tracking, [])
    SENDLE_TRACKING[tracking].append({"event_code": event_code, "event_time": event_time})
    return {"ok": True}
