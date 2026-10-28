"""Server-owned Watchmode catalog refresh and per-title availability lookup."""
from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, AuditLog, ProviderCatalogItem
from app.provider_catalog import ProviderCatalogError
from app.provider_secrets import ProviderSecretError, current_provider_secret

API_URL = "https://api.watchmode.com/v1"
USER_AGENT = "SpotlightApp/1.1 (+https://www.mythicmaskworks.com)"
_REFRESH_LOCK = Lock()


def _request(path: str, key: str, **params):
    url = API_URL + path
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT,
                                    "X-API-Key": key})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ProviderCatalogError(f"Watchmode returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ProviderCatalogError("Watchmode could not be reached or returned invalid data.") from None


def _fetch_catalog(key: str) -> dict[str, list[dict]]:
    catalogs: dict[str, list[dict]] = {"movies": [], "tv": []}
    for category, provider_type in (("movies", "movie"), ("tv", "tv_series")):
        data = _request("/list-titles/", key, types=provider_type, regions="US",
                        source_types="sub,free,rent,buy", sort_by="popularity_desc", page=1, limit=250)
        for row in data.get("titles", []):
            provider_id = row.get("id") or row.get("title_id")
            title = str(row.get("title") or row.get("name") or "").strip()
            if provider_id is None or not title:
                continue
            payload = dict(row)
            payload["id"] = str(provider_id)
            payload["title"] = title
            catalogs[category].append(payload)
    return catalogs


def refresh_watchmode(db: Session, actor: Account) -> dict:
    if not _REFRESH_LOCK.acquire(blocking=False):
        raise ProviderCatalogError("A Watchmode refresh is already in progress.")
    try:
        try:
            key = current_provider_secret(db, "watchmode")
        except ProviderSecretError as exc:
            raise ProviderCatalogError(str(exc)) from None
        if not key:
            raise ProviderCatalogError("Watchmode is not configured on the server yet.")

        catalogs = _fetch_catalog(key)
        changed = {"movies": 0, "tv": 0}
        cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
            ProviderCatalogItem.provider == "watchmode")) or 0)
        now_ms = int(time.time() * 1000)
        for category, items in catalogs.items():
            fetched_ids = set()
            for payload in items:
                provider_id = str(payload["id"])
                fetched_ids.add(provider_id)
                fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                                       ensure_ascii=False).encode("utf-8")).hexdigest()
                row = db.scalar(select(ProviderCatalogItem).where(
                    ProviderCatalogItem.provider == "watchmode",
                    ProviderCatalogItem.category == category,
                    ProviderCatalogItem.provider_id == provider_id,
                ).with_for_update())
                if row is not None and row.fingerprint == fingerprint:
                    continue
                cursor = max(cursor + 1, now_ms)
                if row is None:
                    db.add(ProviderCatalogItem(provider="watchmode", category=category,
                                               provider_id=provider_id, payload=payload,
                                               fingerprint=fingerprint, updated_at_ms=cursor))
                else:
                    row.payload = payload
                    row.fingerprint = fingerprint
                    row.updated_at_ms = cursor
                changed[category] += 1

            # Keep the shared list aligned with Watchmode's current bounded popular page.
            stale = db.scalars(select(ProviderCatalogItem).where(
                ProviderCatalogItem.provider == "watchmode",
                ProviderCatalogItem.category == category,
            )).all()
            for row in stale:
                if row.provider_id not in fetched_ids:
                    db.delete(row)

        db.add(AuditLog(actor_id=actor.id, action="provider_catalog.watchmode_refreshed",
                        entity_type="provider_catalog", entity_id=None,
                        details=f"Changed {changed['movies']} movie and {changed['tv']} TV cards."))
        db.commit()
        latest = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
            ProviderCatalogItem.provider == "watchmode")) or cursor)
        return {"changed": changed, "cursor": latest}
    finally:
        _REFRESH_LOCK.release()


def watchmode_delta(db: Session, since: int = 0) -> dict:
    where = (ProviderCatalogItem.provider == "watchmode",)
    rows = db.scalars(select(ProviderCatalogItem).where(
        *where, ProviderCatalogItem.updated_at_ms > max(0, since)
    ).order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    total = int(db.scalar(select(func.count()).select_from(ProviderCatalogItem).where(*where)) or 0)
    cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(*where)) or 0)
    if since > cursor:
        rows = db.scalars(select(ProviderCatalogItem).where(*where).order_by(
            ProviderCatalogItem.updated_at_ms.asc())).all()
    catalogs = {"movies": [], "tv": []}
    for row in rows:
        if row.category in catalogs:
            catalogs[row.category].append(row.payload)
    return {"available": bool(total), "cursor": cursor,
            "changed": {category: len(items) for category, items in catalogs.items()},
            "catalogs": catalogs}


def watchmode_sources(db: Session, title_id: str) -> dict:
    try:
        key = current_provider_secret(db, "watchmode")
    except ProviderSecretError as exc:
        raise ProviderCatalogError(str(exc)) from None
    if not key:
        raise ProviderCatalogError("Watchmode is not configured on the server yet.")
    if not title_id.isdigit():
        raise ProviderCatalogError("Invalid Watchmode title ID.")
    result = _request(f"/title/{title_id}/sources/", key, regions="US")
    if isinstance(result, list):
        return {"sources": result}
    if not isinstance(result, dict):
        raise ProviderCatalogError("Watchmode returned an invalid availability response.")
    return {"sources": result.get("sources") or []}
