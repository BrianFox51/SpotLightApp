from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Profile, ProfileAvatar, ProfileVisibility
from app.schemas import MeResponse, ProfileUpdate, PublicProfileResponse

router = APIRouter()

MAX_AVATAR_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_AVATAR_STORED_BYTES = 100 * 1024
AVATAR_SIZE = (256, 256)
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _get_visibility(db: DBSession, account_id: str) -> ProfileVisibility:
    visibility = db.get(ProfileVisibility, account_id)
    if visibility is None:
        visibility = ProfileVisibility(account_id=account_id)
        db.add(visibility)
        db.flush()
    return visibility


def _me_payload(account: Account, db: DBSession) -> dict:
    profile = account.profile
    visibility = db.get(ProfileVisibility, account.id)
    avatar = db.get(ProfileAvatar, account.id)
    return {
        "id": account.id,
        "email": account.email,
        "username": account.username,
        "role": account.role,
        "profile": {
            "full_name": profile.full_name if profile else None,
            "state": profile.state if profile else None,
            "zip": profile.zip if profile else None,
            "bio": profile.bio if profile else None,
            "interests": profile.interests if profile else None,
            "site": profile.site if profile else None,
            "avatar_ref": f"/api/v1/profiles/{account.username}/avatar" if avatar else None,
            "show_avatar": visibility.show_avatar if visibility else False,
            "show_state": visibility.show_state if visibility else False,
            "show_bio": visibility.show_bio if visibility else False,
            "show_interests": visibility.show_interests if visibility else False,
            "show_site": visibility.show_site if visibility else False,
        },
    }


@router.get("/me", response_model=MeResponse)
def get_me(
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    return _me_payload(account, db)


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
    changes = payload.model_dump(exclude_unset=True)
    visibility_fields = {
        "show_avatar", "show_state", "show_bio", "show_interests", "show_site"
    }
    visibility_changes = {key: changes.pop(key) for key in visibility_fields if key in changes}
    for field, value in changes.items():
        setattr(profile, field, value)
    if visibility_changes:
        visibility = _get_visibility(db, account.id)
        for field, value in visibility_changes.items():
            setattr(visibility, field, value)
    db.commit()
    db.refresh(account)
    return _me_payload(account, db)


@router.get("/profiles/{username}", response_model=PublicProfileResponse)
def get_public_profile(
    username: str,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    member = db.scalar(select(Account).where(func.lower(Account.username) == username.lower()))
    if member is None or not member.is_active:
        raise HTTPException(status_code=404, detail="Member profile not found.")
    profile = member.profile
    visibility = db.get(ProfileVisibility, member.id)
    avatar = db.get(ProfileAvatar, member.id)
    return {
        "username": member.username,
        # Public Community profiles identify members by username only. Never
        # expose the account holder's private full name through this endpoint.
        "display_name": member.username,
        "role": member.role,
        "created_at": member.created_at,
        "avatar_url": f"/api/v1/profiles/{member.username}/avatar" if avatar and visibility and visibility.show_avatar else None,
        "state": profile.state if profile and visibility and visibility.show_state else None,
        "bio": profile.bio if profile and visibility and visibility.show_bio else None,
        "interests": profile.interests if profile and visibility and visibility.show_interests else None,
        "site": profile.site if profile and visibility and visibility.show_site else None,
    }


@router.get("/profiles/{username}/avatar")
def get_public_avatar(
    username: str,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    member = db.scalar(select(Account).where(func.lower(Account.username) == username.lower()))
    if member is None or not member.is_active:
        raise HTTPException(status_code=404, detail="Profile photo not found.")
    visibility = db.get(ProfileVisibility, member.id)
    avatar = db.get(ProfileAvatar, member.id)
    if not visibility or not visibility.show_avatar or not avatar:
        raise HTTPException(status_code=404, detail="Profile photo not found.")
    return Response(
        content=avatar.image_data,
        media_type=avatar.media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/me/avatar", status_code=status.HTTP_200_OK)
async def upload_avatar(
    file: UploadFile = File(...),
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    raw = await file.read(MAX_AVATAR_UPLOAD_BYTES + 1)
    await file.close()
    if not raw or len(raw) > MAX_AVATAR_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Choose an image smaller than 4 MB.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ALLOWED_IMAGE_FORMATS:
                raise HTTPException(status_code=415, detail="Use a JPEG, PNG, or WebP image.")
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), AVATAR_SIZE)
            encoded = BytesIO()
            quality = 88
            while quality >= 48:
                encoded.seek(0)
                encoded.truncate()
                image.save(encoded, format="WEBP", quality=quality, method=5)
                if encoded.tell() <= MAX_AVATAR_STORED_BYTES:
                    break
                quality -= 8
            if encoded.tell() > MAX_AVATAR_STORED_BYTES:
                raise HTTPException(status_code=422, detail="Could not compress that image below 100 KB.")
            data = encoded.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="That image could not be opened.") from exc

    avatar = db.get(ProfileAvatar, account.id)
    if avatar is None:
        avatar = ProfileAvatar(account_id=account.id, image_data=data, media_type="image/webp")
        db.add(avatar)
    else:
        avatar.image_data = data
        avatar.media_type = "image/webp"
    db.commit()
    return {"message": "Profile photo saved to your Spotlight account.", "size_bytes": len(data)}


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_avatar(
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    avatar = db.get(ProfileAvatar, account.id)
    if avatar:
        db.delete(avatar)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
