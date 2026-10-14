from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from app.database import get_db
from app.dependencies import get_current_account
from app.models import Account, Favorite
from app.schemas import FavoriteCreate, FavoriteResponse
router = APIRouter()
@router.get("/favorites", response_model=list[FavoriteResponse])
def list_favorites(
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    return db.scalars(
        select(Favorite)
        .where(Favorite.account_id == account.id)
        .order_by(Favorite.created_at.desc())
    ).all()
@router.post(
    "/favorites",
    response_model=FavoriteResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_favorite(
    payload: FavoriteCreate,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    category = payload.category.strip()
    provider_id = payload.provider_id.strip()
    if not category or not provider_id:
        raise HTTPException(status_code=422, detail="Category and provider ID are required")
    favorite = Favorite(
        account_id=account.id,
        category=category,
        provider_id=provider_id,
    )
    db.add(favorite)
    try:
        db.commit()
        db.refresh(favorite)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Favorite already exists")
    return favorite
@router.delete("/favorites/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    favorite_id: str,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    favorite = db.scalar(
        select(Favorite).where(
            Favorite.id == favorite_id,
            Favorite.account_id == account.id,
        )
    )
    if favorite is None:
        raise HTTPException(status_code=404, detail="Favorite not found")
    db.delete(favorite)
    db.commit()
