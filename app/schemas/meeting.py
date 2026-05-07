#app/schemas/meeting.py
from pydantic import BaseModel, EmailStr, Field
from typing import List

from datetime import datetime

class MeetingCreateRequest(BaseModel):
    participant_emails: List[EmailStr] = Field(..., min_items=1)
    meeting_title: str
    meeting_body: str
    timezone: str = "Asia/Kolkata"
    start_time: datetime
    duration_minutes: int = 30
    case_id: int

class MeetingCreateResponse(BaseModel):
    status_code: int
    graph_response: dict

class SlotItem(BaseModel):
    start: str
    end: str


class MeetingSlotsResponse(BaseModel):
    booked_slots: List[SlotItem]