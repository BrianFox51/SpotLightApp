import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from app.config import settings
from app.database import get_db
from app.models import Account, LoginAttempt, PasswordResetChallenge, Profile, Session as AccountSession
from app.schemas import AccountResponse, LoginRequest, PasswordResetComplete, RecoveryEmailRequest, RefreshRequest, RegisterRequest, RevokeRequest, TokenResponse
from app.rate_limit import limiter
from app.mailer import send_recovery_email
from app.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
router = APIRouter()
RECOVERY_MESSAGE = "If an account matches that email, recovery instructions have been sent."
LOGIN_MAX_FAILURES = 4
LOGIN_LOCKOUT = timedelta(minutes=15)
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)


def _login_identifier_hash(identifier: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"spotlight-login:{identifier}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _locked_login_error(locked_until: datetime) -> HTTPException:
    now = datetime.now(timezone.utc)
    remaining = max(1, int((locked_until - now).total_seconds() + 0.999))
    minutes = max(1, (remaining + 59) // 60)
    minute_label = "minute" if minutes == 1 else "minutes"
    return HTTPException(
        status_code=423,
        detail=f"Too many failed sign-in attempts. Please wait about {minutes} {minute_label} before trying again.",
        headers={"Retry-After": str(remaining)},
    )


def _get_login_attempt(db: DBSession, identifier_hash: str) -> LoginAttempt | None:
    # This application uses PostgreSQL in production. Insert-if-absent followed
    # by a row lock keeps simultaneous failed attempts from bypassing the limit.
    db.execute(pg_insert(LoginAttempt).values(
        identifier_hash=identifier_hash,
        failed_attempts=0,
        last_failed_at=datetime.now(timezone.utc),
        locked_until=None,
    ).on_conflict_do_nothing(index_elements=[LoginAttempt.identifier_hash]))
    return db.scalar(select(LoginAttempt).where(
        LoginAttempt.identifier_hash == identifier_hash
    ).with_for_update())


def _record_failed_login(db: DBSession, identifier_hash: str) -> HTTPException:
    now = datetime.now(timezone.utc)
    attempt = _get_login_attempt(db, identifier_hash)
    if attempt is None:
        db.rollback()
        return HTTPException(status_code=503, detail="Sign-in is temporarily unavailable. Please try again.")
    if attempt.locked_until and attempt.locked_until > now:
        locked_until = attempt.locked_until
        db.rollback()
        return _locked_login_error(locked_until)
    if attempt.locked_until or attempt.last_failed_at < now - LOGIN_FAILURE_WINDOW:
        attempt.failed_attempts = 0
        attempt.locked_until = None
    attempt.failed_attempts += 1
    attempt.last_failed_at = now
    if attempt.failed_attempts >= LOGIN_MAX_FAILURES:
        attempt.locked_until = now + LOGIN_LOCKOUT
        locked_until = attempt.locked_until
        db.commit()
        return _locked_login_error(locked_until)
    remaining = LOGIN_MAX_FAILURES - attempt.failed_attempts
    db.commit()
    return HTTPException(
        status_code=401,
        detail=f"Username/email or password is incorrect. {remaining} more {('try' if remaining == 1 else 'tries')} available.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _check_login_lockout(db: DBSession, identifier_hash: str) -> None:
    attempt = db.get(LoginAttempt, identifier_hash)
    if attempt and attempt.locked_until:
        now = datetime.now(timezone.utc)
        locked_until = attempt.locked_until
        # PostgreSQL may return a naive timestamp in older deployments.
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise _locked_login_error(locked_until)

def _recovery_code_hash(account_id: str, code: str) -> str:
    material = f"spotlight-password-reset:{account_id}:{code}".encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), material, hashlib.sha256).hexdigest()

def _require_recovery_email():
    if not settings.email_configured:
        raise HTTPException(status_code=503, detail="Email recovery is not configured on the Spotlight server yet.")

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
@limiter.limit(settings.rate_limit_register)
def register(payload: RegisterRequest, request: Request, db: DBSession = Depends(get_db)):
    email = str(payload.email).lower()
    # Keep the capitalization the user chose for display. Login and account
    # uniqueness remain case-insensitive.
    username = payload.username.strip()
    existing = db.scalar(
        select(Account).where(
            or_(Account.email == email, func.lower(Account.username) == username.lower())
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
@limiter.limit(settings.rate_limit_login)
def login(payload: LoginRequest, request: Request, db: DBSession = Depends(get_db)):
    login_identifier = (
        payload.identifier
        if payload.identifier is not None
        else str(payload.email)
    ).strip().lower()

    account = db.scalar(
        select(Account).where(
            or_(
                Account.email == login_identifier,
                func.lower(Account.username) == login_identifier,
            )
        )
    )

    # Key known accounts by account ID so switching between username and email
    # cannot reset the counter. Unknown identifiers receive their own HMAC key.
    lockout_identity = f"account:{account.id}" if account is not None else f"identifier:{login_identifier}"
    identifier_hash = _login_identifier_hash(lockout_identity)
    _check_login_lockout(db, identifier_hash)

    if (
        account is None
        or not account.is_active
        or not verify_password(payload.password, account.password_hash)
    ):
        raise _record_failed_login(db, identifier_hash)

    attempt = db.get(LoginAttempt, identifier_hash)
    if attempt is not None:
        db.delete(attempt)
        db.commit()

    return issue_tokens(db, account)

@router.post("/recovery/username", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_recovery)
def recover_username(
    payload: RecoveryEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
):
    _require_recovery_email()
    email = str(payload.email).strip().lower()
    account = db.scalar(select(Account).where(Account.email == email, Account.is_active.is_(True)))
    if account is not None:
        background_tasks.add_task(
            send_recovery_email,
            account.email,
            "Your SpotLight username",
            f"Your SpotLight username is: {account.username}\n\nIf you did not request this message, you can ignore it.",
        )
    return {"message": RECOVERY_MESSAGE}

@router.post("/recovery/password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_recovery)
def start_password_recovery(
    payload: RecoveryEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
):
    _require_recovery_email()
    email = str(payload.email).strip().lower()
    account = db.scalar(select(Account).where(Account.email == email, Account.is_active.is_(True)))
    if account is not None:
        now = datetime.now(timezone.utc)
        db.query(PasswordResetChallenge).filter(
            PasswordResetChallenge.expires_at <= now
        ).delete(synchronize_session=False)
        requests_in_hour = db.scalar(
            select(func.count()).select_from(PasswordResetChallenge).where(
                PasswordResetChallenge.account_id == account.id,
                PasswordResetChallenge.created_at > now - timedelta(hours=1),
            )
        ) or 0
        if requests_in_hour < 3:
            db.query(PasswordResetChallenge).filter(
                PasswordResetChallenge.account_id == account.id,
                PasswordResetChallenge.consumed_at.is_(None),
            ).update({PasswordResetChallenge.consumed_at: now}, synchronize_session=False)
            code = f"{secrets.randbelow(100_000_000):08d}"
            challenge = PasswordResetChallenge(
                account_id=account.id,
                code_hash=_recovery_code_hash(account.id, code),
                expires_at=now + timedelta(minutes=15),
            )
            db.add(challenge)
            db.commit()
            background_tasks.add_task(
                send_recovery_email,
                account.email,
                "Reset your SpotLight password",
                f"Your SpotLight password reset code is {code}.\n\nIt expires in 15 minutes and can only be used once. If you did not request a reset, ignore this message.",
            )
    return {"message": RECOVERY_MESSAGE}

@router.post("/recovery/password/complete")
@limiter.limit(settings.rate_limit_recovery)
def complete_password_recovery(
    payload: PasswordResetComplete,
    request: Request,
    db: DBSession = Depends(get_db),
):
    email = str(payload.email).strip().lower()
    account = db.scalar(select(Account).where(Account.email == email, Account.is_active.is_(True)))
    now = datetime.now(timezone.utc)
    challenges = []
    if account is not None:
        challenges = db.scalars(
            select(PasswordResetChallenge)
            .where(
                PasswordResetChallenge.account_id == account.id,
                PasswordResetChallenge.consumed_at.is_(None),
                PasswordResetChallenge.expires_at > now,
                PasswordResetChallenge.attempts < 5,
            )
            .order_by(PasswordResetChallenge.created_at.desc())
            .limit(3)
            .with_for_update()
        ).all()
    matched = next((challenge for challenge in challenges if hmac.compare_digest(
        challenge.code_hash, _recovery_code_hash(account.id, payload.code)
    )), None) if account is not None else None
    if matched is None:
        for challenge in challenges:
            challenge.attempts += 1
            if challenge.attempts >= 5:
                challenge.consumed_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="The reset code is invalid or expired.")
    matched.consumed_at = now
    account.password_hash = hash_password(payload.password)
    db.query(AccountSession).filter(AccountSession.account_id == account.id).update(
        {AccountSession.revoked: True}, synchronize_session=False
    )
    db.commit()
    return {"message": "Password reset. Sign in with your new password."}

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
