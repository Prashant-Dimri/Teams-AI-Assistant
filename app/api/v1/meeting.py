#app/api/v1/meeting.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.dependencies import get_db
from app.schemas.meeting import MeetingCreateRequest, MeetingCreateResponse
from app.services.graph_meeting_service import create_teams_meeting, join_meeting_service,get_booked_slots
from datetime import datetime
from app.models.upcoming_meeting import UpcomingMeeting

router = APIRouter(tags=["Meetings"])


@router.post("/create", response_model=MeetingCreateResponse)
def create_meeting(request: MeetingCreateRequest,
                   db: Session = Depends(get_db)):
    try:
        result = create_teams_meeting(request,db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result["status_code"] >= 400:
        raise HTTPException(status_code=result["status_code"], detail=result["graph_response"])

    return result

@router.get("/upcoming-meetings")
def get_upcoming_meetings(db: Session = Depends(get_db)):

    meetings = (
        db.query(UpcomingMeeting)
        .filter(
            UpcomingMeeting.start_time_utc > datetime.utcnow(),
            UpcomingMeeting.status == "scheduled"
        )
        .order_by(UpcomingMeeting.start_time_utc)
        .all()
    )

    return meetings

@router.post("/join-meeting/{meeting_id}")
def join_meeting(meeting_id: int, db: Session = Depends(get_db)):

    meeting = join_meeting_service(meeting_id, db)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
        "message": "Bot joining meeting",
        "meeting_id": meeting.id,
        "case_id": meeting.case_id,
        "join_url": meeting.join_url
    }
    
@router.get("/available-slots")
def available_slots(
    case_id: int,
    date: str,
    timezone: str,
    db: Session = Depends(get_db)
):
    slots = get_booked_slots(case_id, date, timezone, db)

    return {
        "booked_slots": slots
    }