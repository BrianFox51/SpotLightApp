"""Server-owned Twitch OAuth and IGDB catalog refresh/delta feed."""
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

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_API_URL = "https://api.igdb.com/v4/"
USER_AGENT = "SpotlightApp/1.1 (+https://www.mythicmaskworks.com)"
_REFRESH_LOCK = Lock()


def _read_json(request: Request, timeout: int = 25):
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ProviderCatalogError(f"IGDB/Twitch returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ProviderCatalogError("IGDB/Twitch could not be reached or returned invalid data.") from None


def _fetch_catalog(client_id: str, client_secret: str) -> dict[str, list[dict]]:
    body = urlencode({"client_id": client_id, "client_secret": client_secret,
                      "grant_type": "client_credentials"}).encode("ascii")
    token_request = Request(TWITCH_TOKEN_URL, data=body,
                           headers={"User-Agent": USER_AGENT,
                                    "Content-Type": "application/x-www-form-urlencoded",
                                    "Accept": "application/json"})
    auth = _read_json(token_request, timeout=15)
    token = str(auth.get("access_token") or "")
    if not token:
        raise ProviderCatalogError("Twitch did not issue an IGDB access token.")

    now = int(time.time())
    fields = ("id,name,slug,summary,first_release_date,rating,rating_count,"
              "genres.name,platforms.name,cover.url,screenshots.url,videos.video_id,"
              "involved_companies.company.name,involved_companies.developer,"
              "involved_companies.publisher")
    queries = (
        ("popular", f"fields {fields}; where version_parent = null & rating_count > 0; sort rating_count desc; limit 100;"),
        ("upcoming", f"fields {fields}; where version_parent = null & first_release_date > {now}; sort first_release_date asc; limit 100;"),
        ("genres", "fields name; limit 500;"),
        ("platforms", "fields name,abbreviation; limit 500;"),
    )
    catalogs: dict[str, list[dict]] = {}
    for index, (name, query) in enumerate(queries):
        if index:
            time.sleep(0.27)
        request = Request(IGDB_API_URL + ("games" if name in ("popular", "upcoming") else name),
                          data=query.encode("utf-8"),
                          headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                   "Client-ID": client_id, "Authorization": "Bearer " + token,
                                   "Content-Type": "text/plain"})
        payload = _read_json(request)
        if not isinstance(payload, list):
            raise ProviderCatalogError("IGDB returned an invalid catalog response.")
        catalogs[name] = payload
    return catalogs


def refresh_igdb(db: Session, actor: Account) -> dict:
    if not _REFRESH_LOCK.acquire(blocking=False):
        raise ProviderCatalogError("An IGDB refresh is already in progress.")
    try:
        try:
            client_id = current_provider_secret(db, "igdb_client_id")
            client_secret = current_provider_secret(db, "igdb_client_secret")
        except ProviderSecretError as exc:
            raise ProviderCatalogError(str(exc)) from None
        if not client_id or not client_secret:
            raise ProviderCatalogError("Both Twitch/IGDB credentials must be configured on the server.")

        catalogs = _fetch_catalog(client_id, client_secret)
        if not (catalogs.get("popular") or catalogs.get("upcoming")):
            raise ProviderCatalogError("IGDB returned no game titles; the shared catalog was left unchanged.")
        changed = {category: 0 for category in catalogs}
        cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
            ProviderCatalogItem.provider == "igdb")) or 0)
        now_ms = int(time.time() * 1000)
        # All external requests finish before database changes are made.
        for category, items in catalogs.items():
            fetched_ids = set()
            for payload in items:
                provider_id = str(payload.get("id") or "").strip()
                if not provider_id:
                    continue
                fetched_ids.add(provider_id)
                fingerprint = hashlib.sha256(json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")).hexdigest()
                row = db.scalar(select(ProviderCatalogItem).where(
                    ProviderCatalogItem.provider == "igdb",
                    ProviderCatalogItem.category == category,
                    ProviderCatalogItem.provider_id == provider_id,
                ).with_for_update())
                if row is not None and row.fingerprint == fingerprint:
                    continue
                cursor = max(cursor + 1, now_ms)
                if row is None:
                    db.add(ProviderCatalogItem(provider="igdb", category=category,
                                               provider_id=provider_id, payload=payload,
                                               fingerprint=fingerprint, updated_at_ms=cursor))
                else:
                    row.payload = payload
                    row.fingerprint = fingerprint
                    row.updated_at_ms = cursor
                changed[category] += 1

            # Popular and upcoming are bounded feeds. Remove titles that no
            # longer belong so membership snapshots can clear desktop flags.
            if category in ("popular", "upcoming"):
                stale = db.scalars(select(ProviderCatalogItem).where(
                    ProviderCatalogItem.provider == "igdb",
                    ProviderCatalogItem.category == category,
                )).all()
                for row in stale:
                    if row.provider_id not in fetched_ids:
                        db.delete(row)

        db.add(AuditLog(actor_id=actor.id, action="provider_catalog.igdb_refreshed",
                        entity_type="provider_catalog", entity_id=None,
                        details=(f"Changed {changed['popular']} popular and {changed['upcoming']} upcoming games; "
                                 f"{changed['genres']} genres and {changed['platforms']} platforms.")))
        db.commit()
        latest = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
            ProviderCatalogItem.provider == "igdb")) or cursor)
        return {"changed": changed, "cursor": latest}
    finally:
        _REFRESH_LOCK.release()


def igdb_delta(db: Session, since: int = 0) -> dict:
    where = (ProviderCatalogItem.provider == "igdb",)
    cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(*where)) or 0)
    total = int(db.scalar(select(func.count()).select_from(ProviderCatalogItem).where(*where)) or 0)
    if since > cursor:
        since = 0
    changed_rows = db.scalars(select(ProviderCatalogItem).where(
        *where, ProviderCatalogItem.updated_at_ms > max(0, since)
    ).order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    catalogs = {"popular": [], "upcoming": [], "genres": [], "platforms": []}
    for row in changed_rows:
        if row.category in catalogs:
            catalogs[row.category].append(row.payload)
    # Dictionary rows are small and included on each read so changed game cards
    # can always resolve their genre and platform IDs offline.
    for category in ("genres", "platforms"):
        catalogs[category] = db.scalars(select(ProviderCatalogItem.payload).where(
            ProviderCatalogItem.provider == "igdb", ProviderCatalogItem.category == category
        ).order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    membership = {}
    for category in ("popular", "upcoming"):
        membership[category] = db.scalars(select(ProviderCatalogItem.provider_id).where(
            ProviderCatalogItem.provider == "igdb", ProviderCatalogItem.category == category
        )).all()
    changed = {category: len(catalogs[category]) for category in catalogs}
    return {"available": bool(total), "cursor": cursor, "changed": changed,
            "membership": membership, "catalogs": catalogs}
