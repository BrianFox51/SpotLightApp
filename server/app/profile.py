from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Profile
from app.schemas import MeResponse, ProfileUpdate
router = APIRouter()
@router.get("/me", response_model=MeResponse)
def get_me(
    account: Account = Depends(get_current_account),
):
    return {"id": account.id, "email": account.email, "username": account.username, "role": account.role, "profile": account.profile}
@router.patch("/me", response_model=MeResponse)
def update_me(
    payload: ProfileUpdate,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    profile = account.profile
    if profile is None:
        profile = Profile(account_id=account.id)
        db.add(profile)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return {
        "id": account.id,
        "email": account.email,
        "username": account.username,
        "role": account.role,
        "profile": profile,
    }
