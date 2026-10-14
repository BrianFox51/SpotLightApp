from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.database import get_db
from app.dependencies import get_admin_account
from app.models import Account, AuditLog, ModerationLog, Submission
from app.schemas import ModerationRequest, SubmissionResponse
router = APIRouter()
@router.get("/admin/submissions", response_model=list[SubmissionResponse])
def list_pending_submissions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    return db.scalars(
        select(Submission)
        .where(Submission.status == "pending")
        .order_by(Submission.submitted_at.asc())
        .offset(offset)
        .limit(limit)
    ).all()
@router.post(
    "/admin/submissions/{submission_id}/moderation",
    response_model=SubmissionResponse,
)
def review_submission(
    submission_id: str,
    payload: ModerationRequest,
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    submission = db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .with_for_update()
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.status != "pending":
        raise HTTPException(status_code=409, detail="Submission has already been reviewed")
    submission.status = "approved" if payload.action == "approve" else "rejected"
    reason = payload.reason.strip() if payload.reason else None
    db.add(
        ModerationLog(
            submission_id=submission.id,
            reviewer_id=account.id,
            action=payload.action,
            reason=reason,
        )
    )
    db.add(
        AuditLog(
            actor_id=account.id,
            action=f"submission.{submission.status}",
            entity_type="submission",
            entity_id=submission.id,
            details=reason,
        )
    )
    db.commit()
    db.refresh(submission)
    return submission
