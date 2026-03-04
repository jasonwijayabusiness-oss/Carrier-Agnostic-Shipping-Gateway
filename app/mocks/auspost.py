from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import random
import requests

router = APIRouter(prefix="/mock/auspost", tags=["mock_auspost"])

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@router.post("/labels")
def create_label(payload: dict):
    tracking = f"AUSPOST-TRACK-{random.randint(100000, 999999)}"
    label_url = f"https://labels.auspost.mock/{tracking}.pdf"
    return {"tracking_number": tracking, "label_url": label_url}

@router.post("/push_event")
def push_event(payload: dict):
    tracking_number = payload.get("tracking_number")
    event_code = payload.get("event_code")
    event_time = payload.get("event_time") or now_iso()
    if not tracking_number or not event_code:
        raise HTTPException(status_code=400, detail="tracking_number and event_code required")
    orchestrator_url = payload.get("orchestrator_url") or "http://127.0.0.1:8000/webhooks/tracking/AUSPOST"
    r = requests.post(orchestrator_url, json={"tracking_number": tracking_number, "event_code": event_code, "event_time": event_time}, timeout=5)
    return {"status_code": r.status_code}
