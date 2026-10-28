import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_admin_account, get_current_account
from app.models import Account
from app.provider_catalog import ProviderCatalogError, refresh_tmdb, tmdb_delta
from app.ticketmaster_catalog import refresh_ticketmaster, ticketmaster_delta
from app.schemas import TicketmasterCatalogRefreshRequest
from app.rate_limit import limiter
from app.config import settings

router = APIRouter()
_TICKETMASTER_SCOPE = re.compile(r"^(?:state:[A-Z]{2}|local:-?\d{1,3}\.\d{2},-?\d{1,3}\.\d{2})$")


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


@router.get("/catalog/ticketmaster")
def get_ticketmaster_catalog(
    scope: str = Query(min_length=8, max_length=48),
    since: int = Query(default=0, ge=0),
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    if not _TICKETMASTER_SCOPE.fullmatch(scope):
        raise HTTPException(status_code=422, detail="Invalid Ticketmaster search area.")
    return ticketmaster_delta(db, scope, since)


@router.post("/catalog/ticketmaster/refresh")
@limiter.limit(settings.rate_limit_provider_refresh)
def refresh_ticketmaster_catalog(
    request: Request,
    payload: TicketmasterCatalogRefreshRequest,
    account: Account = Depends(get_current_account),
    db: DBSession = Depends(get_db),
):
    try:
        return refresh_ticketmaster(db, account, state_code=payload.state_code,
                                    latitude=payload.latitude, longitude=payload.longitude,
                                    radius=payload.radius)
    except ProviderCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
