from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Submission
from app.schemas import SubmissionCreate, SubmissionResponse
router = APIRouter()
@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_submission(
    payload: SubmissionCreate,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    event_type = payload.event_type.strip()
    venue = payload.venue.strip()
    if not event_type or not venue:
        raise HTTPException(status_code=422, detail="Event type and venue are required")
    submission = Submission(
        account_id=account.id,
        event_type=event_type,
        venue=venue,
        public_link=str(payload.public_link) if payload.public_link else None,
        event_date_start=payload.event_date_start,
        event_date_end=payload.event_date_end,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission
@router.get("/submissions/mine", response_model=list[SubmissionResponse])
def list_my_submissions(
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    return db.scalars(
        select(Submission)
        .where(Submission.account_id == account.id)
        .order_by(Submission.submitted_at.desc())
    ).all()
@router.get("/community/submissions", response_model=list[SubmissionResponse])
def community_feed(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db),
):
    return db.scalars(
        select(Submission)
        .where(Submission.status == "approved")
        .order_by(Submission.event_date_start.asc())
        .offset(offset)
        .limit(limit)
    ).all()
