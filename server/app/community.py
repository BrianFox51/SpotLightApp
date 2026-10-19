from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_admin_account, get_current_account
from app.models import Account, AuditLog, CommunityPost, CommunityReply, CommunityReport
from app.rate_limit import limiter
from app.schemas import (
    CommunityContentModerationRequest,
    CommunityModerationRequest,
    CommunityPostCreate,
    CommunityReplyCreate,
    CommunityReportCreate,
)
from app.config import settings

router = APIRouter()


def _post_dict(post: CommunityPost, username: str, reply_count: int) -> dict:
    return {
        "id": post.id,
        "category": post.category,
        "title": post.title,
        "body": post.body,
        "author": username,
        "reply_count": reply_count,
        "created_at": post.created_at,
    }


@router.get("/community/posts")
def list_posts(
    category: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    reply_count = func.count(CommunityReply.id)
    statement = (
        select(CommunityPost, Account.username, reply_count)
        .join(Account, Account.id == CommunityPost.account_id)
        .outerjoin(
            CommunityReply,
            (CommunityReply.post_id == CommunityPost.id) & (CommunityReply.hidden.is_(False)),
        )
        .where(CommunityPost.hidden.is_(False))
        .group_by(CommunityPost.id, Account.username)
        .order_by(CommunityPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if category:
        statement = statement.where(CommunityPost.category == category)
    rows = db.execute(statement).all()
    return [_post_dict(post, username, count) for post, username, count in rows]


@router.post("/community/posts", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_community)
def create_post(
    payload: CommunityPostCreate,
    request: Request,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    title, body = payload.title.strip(), payload.body.strip()
    if len(title) < 4 or not body:
        raise HTTPException(status_code=422, detail="Add a title and message to your discussion.")
    post = CommunityPost(account_id=account.id, category=payload.category, title=title, body=body)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_dict(post, account.username, 0)


@router.get("/community/posts/{post_id}/replies")
def list_replies(
    post_id: str,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.hidden.is_(False)))
    if post is None:
        raise HTTPException(status_code=404, detail="Discussion not found.")
    rows = db.execute(
        select(CommunityReply, Account.username)
        .join(Account, Account.id == CommunityReply.account_id)
        .where(CommunityReply.post_id == post_id, CommunityReply.hidden.is_(False))
        .order_by(CommunityReply.created_at.asc())
    ).all()
    return [{"id": reply.id, "body": reply.body, "author": username, "created_at": reply.created_at}
            for reply, username in rows]


@router.post("/community/posts/{post_id}/replies", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_community)
def create_reply(
    post_id: str,
    payload: CommunityReplyCreate,
    request: Request,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.hidden.is_(False)))
    if post is None:
        raise HTTPException(status_code=404, detail="Discussion not found.")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Reply text is required.")
    reply = CommunityReply(post_id=post_id, account_id=account.id, body=body)
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return {"id": reply.id, "body": reply.body, "author": account.username, "created_at": reply.created_at}


@router.post("/community/reports", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
def report_content(
    payload: CommunityReportCreate,
    request: Request,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    if payload.target_type == "post":
        target = db.get(CommunityPost, payload.target_id)
        if target is None or target.hidden:
            raise HTTPException(status_code=404, detail="Community content not found.")
        post_id, reply_id = target.id, None
        owner_id = target.account_id
    else:
        target = db.get(CommunityReply, payload.target_id)
        if target is None or target.hidden:
            raise HTTPException(status_code=404, detail="Community content not found.")
        parent = db.get(CommunityPost, target.post_id)
        if parent is None or parent.hidden:
            raise HTTPException(status_code=404, detail="Community content not found.")
        post_id, reply_id = None, target.id
        owner_id = target.account_id
    if owner_id == account.id:
        raise HTTPException(status_code=400, detail="You cannot report your own content.")
    existing = db.scalar(select(CommunityReport.id).where(
        CommunityReport.reporter_id == account.id,
        CommunityReport.post_id == post_id,
        CommunityReport.reply_id == reply_id,
        CommunityReport.status == "pending",
    ))
    if existing:
        return {"message": "Thank you. This content is already awaiting moderator review."}
    report = CommunityReport(
        reporter_id=account.id,
        post_id=post_id,
        reply_id=reply_id,
        reason=payload.reason.strip(),
    )
    db.add(report)
    db.commit()
    return {"message": "Thank you. Your report was sent to the Spotlight moderators."}


@router.get("/admin/community/reports")
def list_community_reports(
    limit: int = Query(default=50, ge=1, le=100),
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    reports = db.scalars(
        select(CommunityReport)
        .where(CommunityReport.status == "pending")
        .order_by(CommunityReport.created_at.asc())
        .limit(limit)
    ).all()
    output = []
    for report in reports:
        if report.post_id:
            target = db.get(CommunityPost, report.post_id)
            target_type = "post"
            content = {"title": target.title, "body": target.body} if target else {}
        else:
            target = db.get(CommunityReply, report.reply_id)
            target_type = "reply"
            content = {"body": target.body} if target else {}
        reporter = db.get(Account, report.reporter_id)
        output.append({
            "id": report.id,
            "target_type": target_type,
            "target_id": report.post_id or report.reply_id,
            "reason": report.reason,
            "reporter": reporter.username if reporter else "Deleted account",
            "content": content,
            "created_at": report.created_at,
        })
    return output


@router.post("/admin/community/reports/{report_id}/moderation")
def moderate_community_report(
    report_id: str,
    payload: CommunityModerationRequest,
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    report = db.scalar(select(CommunityReport).where(CommunityReport.id == report_id).with_for_update())
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    if report.status != "pending":
        raise HTTPException(status_code=409, detail="Report has already been reviewed.")
    if payload.action == "hide":
        if report.post_id:
            target = db.get(CommunityPost, report.post_id)
        else:
            target = db.get(CommunityReply, report.reply_id)
        if target is not None:
            target.hidden = True
    report.status = "reviewed"
    report.reviewed_by = account.id
    report.reviewed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        actor_id=account.id,
        action=f"community_report.{payload.action}",
        entity_type="community_report",
        entity_id=report.id,
        details=payload.reason,
    ))
    db.commit()
    return {"status": report.status, "action": payload.action}


@router.post("/admin/community/content/{target_type}/{target_id}/moderation")
def moderate_community_content(
    target_type: str,
    target_id: str,
    payload: CommunityContentModerationRequest,
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    if target_type == "post":
        model = CommunityPost
    elif target_type == "reply":
        model = CommunityReply
    else:
        raise HTTPException(status_code=404, detail="Community content not found.")
    target = db.scalar(select(model).where(model.id == target_id).with_for_update())
    if target is None:
        raise HTTPException(status_code=404, detail="Community content not found.")
    target.hidden = payload.action == "hide"
    reason = payload.reason.strip() or None
    db.add(AuditLog(
        actor_id=account.id,
        action=f"community_{target_type}.{payload.action}",
        entity_type=f"community_{target_type}",
        entity_id=target.id,
        details=reason,
    ))
    db.commit()
    return {"status": "hidden" if target.hidden else "visible", "target_type": target_type}


@router.get("/admin/community/hidden")
def list_hidden_community_content(
    limit: int = Query(default=100, ge=1, le=200),
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    posts = db.execute(
        select(CommunityPost, Account.username)
        .join(Account, Account.id == CommunityPost.account_id)
        .where(CommunityPost.hidden.is_(True))
        .order_by(CommunityPost.created_at.desc())
        .limit(limit)
    ).all()
    replies = db.execute(
        select(CommunityReply, Account.username)
        .join(Account, Account.id == CommunityReply.account_id)
        .where(CommunityReply.hidden.is_(True))
        .order_by(CommunityReply.created_at.desc())
        .limit(limit)
    ).all()
    output = [
        {"target_type": "post", "id": item.id, "title": item.title, "body": item.body,
         "category": item.category, "author": username, "created_at": item.created_at}
        for item, username in posts
    ]
    output.extend(
        {"target_type": "reply", "id": item.id, "title": "Reply", "body": item.body,
         "category": "", "author": username, "created_at": item.created_at}
        for item, username in replies
    )
    return sorted(output, key=lambda item: item["created_at"], reverse=True)[:limit]
