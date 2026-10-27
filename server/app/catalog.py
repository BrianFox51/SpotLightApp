from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_admin_account, get_current_account
from app.models import Account
from app.provider_catalog import ProviderCatalogError, refresh_tmdb, tmdb_delta
from app.rate_limit import limiter
from app.config import settings

router = APIRouter()


@router.get("/catalog/tmdb")
def get_tmdb_catalog(
    since: int = Query(default=0, ge=0),
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    """Return server-shared TMDB cards changed since a desktop's last cursor."""
    return tmdb_delta(db, since)


@router.post("/admin/catalog/tmdb/refresh")
@limiter.limit(settings.rate_limit_provider_refresh)
def refresh_tmdb_catalog(
    request: Request,
    account: Account = Depends(get_admin_account),
    db: DBSession = Depends(get_db),
):
    try:
        return refresh_tmdb(db, account)
    except ProviderCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
