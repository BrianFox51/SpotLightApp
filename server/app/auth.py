import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from app.config import settings
from app.database import get_db
from app.models import Account, Profile, Session as AccountSession
from app.schemas import AccountResponse, LoginRequest, RefreshRequest, RegisterRequest, RevokeRequest, TokenResponse
from app.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
router = APIRouter()
def issue_tokens(db: DBSession, account: Account) -> TokenResponse:
    raw_token, token_hash = create_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    db.add(
        AccountSession(
            account_id=account.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    db.commit()
    return TokenResponse(
        access_token=create_access_token(account.id),
        refresh_token=raw_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )
@router.post("/register", response_model=AccountResponse, status_code=201)
def register(payload: RegisterRequest, db: DBSession = Depends(get_db)):
    email = str(payload.email).lower()
    username = payload.username.lower()
    existing = db.scalar(
        select(Account).where(
            or_(Account.email == email, Account.username == username)
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email or username is already in use",
        )
    account = Account(
        email=email,
        username=username,
        password_hash=hash_password(payload.password),
        role="user",
    )
    db.add(account)
    try:
        db.flush()
        db.add(Profile(account_id=account.id))
        db.commit()
        db.refresh(account)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or username is already in use",
        )
    return account

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DBSession = Depends(get_db)):
    login_identifier = (
        payload.identifier
        if payload.identifier is not None
        else str(payload.email)
    ).strip().lower()

    account = db.scalar(
        select(Account).where(
            or_(
                Account.email == login_identifier,
                Account.username == login_identifier,
            )
        )
    )

    if (
        account is None
        or not account.is_active
        or not verify_password(payload.password, account.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email, username, or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return issue_tokens(db, account)
@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: DBSession = Depends(get_db)):
    token_hash = hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest()
    session = db.scalar(
        select(AccountSession)
        .where(AccountSession.token_hash == token_hash)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if session is None or session.revoked or session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    account = db.get(Account, session.account_id)
    if account is None or not account.is_active:
        session.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    session.revoked = True
    return issue_tokens(db, account)
@router.post("/revoke")
def revoke(payload: RevokeRequest, db: DBSession = Depends(get_db)):
    token_hash = hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest()
    session = db.scalar(
        select(AccountSession).where(AccountSession.token_hash == token_hash)
    )
    if session is not None and not session.revoked:
        session.revoked = True
        db.commit()
    return {"status": "revoked"}
