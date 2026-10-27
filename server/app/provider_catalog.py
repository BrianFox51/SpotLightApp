"""Server-owned TMDB refresh and per-card delta storage."""
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
from app.provider_secrets import ProviderSecretError, current_provider_secret

TMDB_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/"
USER_AGENT = "SpotlightApp/1.1 (+https://www.mythicmaskworks.com)"
_REFRESH_LOCK = Lock()


class ProviderCatalogError(RuntimeError):
    pass


def _request_tmdb(path: str, key: str, **params):
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if len(key) > 40:
        headers["Authorization"] = "Bearer " + key
    else:
        params["api_key"] = key
    url = TMDB_BASE + path + "?" + urlencode(params)
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Never surface the request URL: v3 keys are query parameters.
        raise ProviderCatalogError(f"TMDB returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ProviderCatalogError("TMDB could not be reached or returned invalid data.") from None


def _fetch_tmdb(key: str) -> dict[str, list[dict]]:
    catalogs: dict[str, list[dict]] = {}
    for category, endpoint, genre_endpoint, title_key, date_key in (
        ("movies", "/movie/now_playing", "/genre/movie/list", "title", "release_date"),
        ("tv", "/tv/on_the_air", "/genre/tv/list", "name", "first_air_date"),
    ):
        genre_data = _request_tmdb(genre_endpoint, key, language="en-US")
        genres = {
            int(genre["id"]): str(genre.get("name") or "Other")
            for genre in genre_data.get("genres", [])
            if genre.get("id") is not None
        }
        params = {"language": "en-US", "page": 1}
        if category == "movies":
            params["region"] = "US"
        else:
            params["timezone"] = "America/New_York"
        result_data = _request_tmdb(endpoint, key, **params)
        items = []
        for row in result_data.get("results", []):
            title = str(row.get(title_key) or "").strip()
            provider_id = row.get("id")
            if not title or provider_id is None:
                continue
            raw_genre = next((genres.get(int(value)) for value in row.get("genre_ids", [])
                              if str(value).isdigit() and int(value) in genres), "Other")
            genre = {"Science Fiction": "Sci-Fi", "Action & Adventure": "Action", "Documentary": "Docs"}.get(raw_genre, raw_genre)
            date = str(row.get(date_key) or "")
            try:
                score = round(float(row.get("vote_average") or 0) * 10, 1)
            except (TypeError, ValueError):
                score = 0
            kind = "movie" if category == "movies" else "tv"
            items.append({
                "id": provider_id,
                "title": title,
                "year": date[:4],
                "date": date,
                "overview": str(row.get("overview") or ""),
                "score": score,
                "genre": genre,
                "poster": IMAGE_BASE + "w500" + row["poster_path"] if row.get("poster_path") else "",
                "url": f"https://www.themoviedb.org/{kind}/{provider_id}",
            })
        catalogs[category] = items
    return catalogs


def _serialize(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def refresh_tmdb(db: Session, actor: Account) -> dict:
    if not _REFRESH_LOCK.acquire(blocking=False):
        raise ProviderCatalogError("A TMDB refresh is already in progress.")
    try:
        return _refresh_tmdb_locked(db, actor)
    finally:
        _REFRESH_LOCK.release()


def _refresh_tmdb_locked(db: Session, actor: Account) -> dict:
    try:
        key = current_provider_secret(db, "tmdb")
    except ProviderSecretError as exc:
        raise ProviderCatalogError(str(exc)) from None
    if not key:
        raise ProviderCatalogError("TMDB is not configured on the server yet.")

    # Fetch all feeds before writing, so a provider failure cannot leave a partial update.
    catalogs = _fetch_tmdb(key)
    changed = {"movies": 0, "tv": 0}
    cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
        ProviderCatalogItem.provider == "tmdb")) or int(time.time() * 1000))
    for category in ("movies", "tv"):
        for payload in catalogs[category]:
            provider_id = str(payload["id"])
            fingerprint = hashlib.sha256(_serialize(payload).encode("utf-8")).hexdigest()
            row = db.scalar(select(ProviderCatalogItem).where(
                ProviderCatalogItem.provider == "tmdb",
                ProviderCatalogItem.category == category,
                ProviderCatalogItem.provider_id == provider_id,
            ).with_for_update())
            if row is not None and row.fingerprint == fingerprint:
                continue
            cursor = max(cursor + 1, int(time.time() * 1000))
            if row is None:
                row = ProviderCatalogItem(
                    provider="tmdb", category=category, provider_id=provider_id,
                    payload=payload, fingerprint=fingerprint, updated_at_ms=cursor,
                )
                db.add(row)
            else:
                row.payload = payload
                row.fingerprint = fingerprint
                row.updated_at_ms = cursor
            changed[category] += 1

    db.add(AuditLog(
        actor_id=actor.id,
        action="provider_catalog.tmdb_refreshed",
        entity_type="provider_catalog",
        entity_id=None,
        details=f"Changed {changed['movies']} movie and {changed['tv']} TV cards.",
    ))
    db.commit()
    latest_cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
        ProviderCatalogItem.provider == "tmdb")) or cursor)
    return {"changed": changed, "cursor": latest_cursor}


def tmdb_delta(db: Session, since: int = 0) -> dict:
    rows = db.scalars(select(ProviderCatalogItem).where(
        ProviderCatalogItem.provider == "tmdb",
        ProviderCatalogItem.updated_at_ms > max(0, since),
    ).order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    total = db.scalar(select(func.count()).select_from(ProviderCatalogItem).where(
        ProviderCatalogItem.provider == "tmdb")) or 0
    cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
        ProviderCatalogItem.provider == "tmdb")) or 0)
    if since > cursor:
        # A restored server database may be older than this desktop's saved cursor.
        rows = db.scalars(select(ProviderCatalogItem).where(
            ProviderCatalogItem.provider == "tmdb",
        ).order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    catalogs = {"movies": [], "tv": []}
    for row in rows:
        catalogs[row.category].append(row.payload)
    return {
        "available": bool(total),
        "cursor": cursor,
        "changed": {"movies": len(catalogs["movies"]), "tv": len(catalogs["tv"])},
        "catalogs": catalogs,
    }
