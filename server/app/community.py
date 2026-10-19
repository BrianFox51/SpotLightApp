from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from io import BytesIO
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_admin_account, get_current_account
from app.models import Account, AuditLog, CommunityAttachment, CommunityPost, CommunityReply, CommunityReport
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
MAX_COMMUNITY_IMAGE_UPLOAD = 4 * 1024 * 1024
MAX_COMMUNITY_IMAGE_STORED = 600 * 1024
MAX_COMMUNITY_IMAGES_PER_POST = 4


class _CommunityBodySanitizer(HTMLParser):
    """Preserve only the rich-text subset used by the desktop post composer."""
    _families = {"Segoe UI", "Arial", "Georgia", "Times New Roman", "Courier New"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag in {"b", "strong", "i", "em", "u"}:
            normalized = {"strong": "b", "em": "i"}.get(tag, tag)
            self.parts.append(f"<{normalized}>")
            self.stack.append((tag, f"</{normalized}>"))
            return
        if tag != "span":
            self.stack.append((tag, ""))
            return
        raw_style = dict(attrs).get("style", "")
        declarations = dict(part.split(":", 1) for part in raw_style.split(";") if ":" in part)
        styles = []
        family = declarations.get("font-family", "")
        if family in self._families: styles.append(f"font-family:{family}")
        size = declarations.get("font-size", "")
        if re.fullmatch(r"(?:10|11|12|13|14|16|18|20|24)px", size): styles.append(f"font-size:{size}")
        if declarations.get("font-weight") == "bold": styles.append("font-weight:bold")
        if declarations.get("font-style") == "italic": styles.append("font-style:italic")
        if declarations.get("text-decoration") == "underline": styles.append("text-decoration:underline")
        opening = f'<span style="{escape(";".join(styles), quote=True)}">' if styles else ""
        self.parts.append(opening)
        self.stack.append((tag, "</span>" if opening else ""))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                for _tag, closing in reversed(self.stack[index:]):
                    if closing: self.parts.append(closing)
                del self.stack[index:]
                break

    def handle_data(self, data): self.parts.append(escape(data))

    def finish(self):
        for _tag, closing in reversed(self.stack):
            if closing: self.parts.append(closing)
        self.stack.clear()
        return "".join(self.parts).strip()


def _sanitize_community_body(value: str) -> str:
    sanitizer = _CommunityBodySanitizer()
    sanitizer.feed(value)
    return sanitizer.finish()


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
    title, body = payload.title.strip(), _sanitize_community_body(payload.body)
    if len(title) < 4 or not body:
        raise HTTPException(status_code=422, detail="Add a title and message to your discussion.")
    post = CommunityPost(account_id=account.id, category=payload.category, title=title, body=body)
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_dict(post, account.username, 0)


@router.get("/community/posts/{post_id}/images")
def list_post_images(
    post_id: str,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.hidden.is_(False)))
    if post is None:
        raise HTTPException(status_code=404, detail="Discussion not found.")
    images = db.scalars(select(CommunityAttachment).where(CommunityAttachment.post_id == post_id)
                        .order_by(CommunityAttachment.created_at.asc())).all()
    return [{"id": image.id, "media_type": image.media_type,
             "url": f"/api/v1/community/posts/{post_id}/images/{image.id}"} for image in images]


@router.post("/community/posts/{post_id}/images", status_code=status.HTTP_201_CREATED)
async def upload_post_image(
    post_id: str,
    file: UploadFile = File(...),
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.hidden.is_(False)))
    if post is None:
        raise HTTPException(status_code=404, detail="Discussion not found.")
    if post.account_id != account.id and account.role != "admin":
        raise HTTPException(status_code=403, detail="Only the discussion author or an administrator can add images.")
    count = db.scalar(select(func.count(CommunityAttachment.id)).where(CommunityAttachment.post_id == post_id)) or 0
    if count >= MAX_COMMUNITY_IMAGES_PER_POST:
        raise HTTPException(status_code=422, detail="A discussion can include up to four photos.")
    raw = await file.read(MAX_COMMUNITY_IMAGE_UPLOAD + 1)
    await file.close()
    if not raw or len(raw) > MAX_COMMUNITY_IMAGE_UPLOAD:
        raise HTTPException(status_code=413, detail="Each photo must be smaller than 4 MB.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Use a JPEG, PNG, or WebP photo.")
            if source.width * source.height > 40_000_000:
                raise HTTPException(status_code=413, detail="That photo has too many pixels to upload safely.")
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            encoded = BytesIO()
            quality = 86
            while quality >= 46:
                encoded.seek(0)
                encoded.truncate()
                image.save(encoded, format="WEBP", quality=quality, method=5)
                if encoded.tell() <= MAX_COMMUNITY_IMAGE_STORED:
                    break
                quality -= 8
            if encoded.tell() > MAX_COMMUNITY_IMAGE_STORED:
                raise HTTPException(status_code=422, detail="Could not compress this photo below 600 KB.")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="That photo could not be opened.") from exc
    attachment = CommunityAttachment(post_id=post.id, account_id=account.id,
                                     image_data=encoded.getvalue(), media_type="image/webp")
    db.add(attachment)
    db.commit()
    return {"id": attachment.id, "media_type": attachment.media_type}


@router.get("/community/posts/{post_id}/images/{image_id}")
def get_post_image(
    post_id: str,
    image_id: str,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.hidden.is_(False)))
    image = db.scalar(select(CommunityAttachment).where(
        CommunityAttachment.id == image_id, CommunityAttachment.post_id == post_id
    ))
    if post is None or image is None:
        raise HTTPException(status_code=404, detail="Photo not found.")
    return Response(content=image.image_data, media_type=image.media_type,
                    headers={"Cache-Control": "private, max-age=3600"})


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
