from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import Account
from jose import jwt
bearer_scheme = HTTPBearer(auto_error=False)
def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Account:
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=["HS256"],
        )
    except JWTError:
        raise unauthorized
    if payload.get("type") != "access":
        raise unauthorized
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise unauthorized
    account = db.get(Account, subject)
    if account is None or not account.is_active:
        raise unauthorized
    return account
def get_admin_account(
    account: Account = Depends(get_current_account),
) -> Account:
    if account.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return account
