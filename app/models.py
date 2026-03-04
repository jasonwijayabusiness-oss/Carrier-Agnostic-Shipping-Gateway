from pydantic import BaseModel, Field
from typing import Optional, List

class SeedOrdersRequest(BaseModel):
    n: int = Field(20, ge=1, le=500)

class CreateLabelRequest(BaseModel):
    order_id: str

class PushEventRequest(BaseModel):
    tracking_number: str
    event_code: str
    event_time: Optional[str] = None

class TrackingEvent(BaseModel):
    provider: str
    event_code: str
    canonical_status: str
    event_time: str
    received_time: str

class TrackingResponse(BaseModel):
    tracking_number: str
    events: List[TrackingEvent]
