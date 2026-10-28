"""Server-owned Ticketmaster event refresh and scoped changed-card feed."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, AuditLog, ProviderCatalogItem
from app.provider_catalog import ProviderCatalogError
from app.provider_secrets import ProviderSecretError, current_provider_secret

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
USER_AGENT = "SpotlightApp/1.1 (+https://www.mythicmaskworks.com)"
SPORTS = {
    "baseball": "Baseball", "basketball": "Basketball", "football": "Football", "hockey": "Hockey",
    "soccer": "Soccer", "golf": "Golf", "tennis": "Tennis", "boxing": "MMA & Boxing",
    "martial arts": "MMA & Boxing", "mma": "MMA & Boxing", "wrestling": "Wrestling", "rodeo": "Rodeo",
    "motorsports": "Racing", "racing": "Racing", "poker": "Poker", "bowling": "Bowling",
    "esports": "Esports", "darts": "Darts", "billiards": "Pool & Billiards",
}
FEST = [
    (("pumpkin", "harvest", "corn", "food", "taste", "wine", "beer", "apple", "chili", "bbq", "brat"), "Harvest & Food"),
    (("fair", "expo"), "County & State Fairs"), (("parade", "christmas", "holiday", "fireworks", "lights"), "Parades & Holidays"),
    (("film",), "Film Festivals"), (("art", "craft"), "Arts & Crafts"), (("car show", "auto", "motor"), "Car Shows"),
    (("renaissance", "faire", "fantasy", "comic"), "Renaissance & Fantasy"),
    (("music", "jazz", "blues", "rock", "fest"), "Music Festivals"),
]
_REFRESH_LOCK = Lock()
_REQUEST_LOCK = Lock()
_LAST_REQUEST_AT = 0.0


def _norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _scope(state_code: str | None, latitude: float | None, longitude: float | None) -> str:
    if state_code:
        return "state:" + state_code.strip().upper()
    if latitude is None or longitude is None:
        raise ProviderCatalogError("Ticketmaster needs a state or local search area.")
    return f"local:{latitude:.2f},{longitude:.2f}"


def _genre_music(event: dict) -> str:
    text = _norm(event["genre"] + " " + event["sub"])
    if any(word in text for word in ("hip hop", "rap")): return "Hip-Hop"
    if any(word in text for word in ("r b", "rnb", "rhythm and blues", "soul")): return "R&B"
    if any(word in text for word in ("electronic", "edm", "dance")): return "Electronic"
    if any(word in text for word in ("latin", "salsa", "reggaeton")): return "Latin"
    if "country" in text: return "Country"
    if "jazz" in text: return "Jazz"
    if "pop" in text: return "Pop"
    if any(word in text for word in ("rock", "metal", "punk", "alternative", "indie")): return "Rock"
    return "Other"


def _genre_sports(event: dict) -> str:
    text = _norm(event["genre"] + " " + event["sub"] + " " + event["name"])
    return next((value for word, value in SPORTS.items() if word in text), "Other")


def _genre_festival(event: dict) -> str:
    text = _norm(event["name"])
    return next((genre for words, genre in FEST if any(word in text for word in words)), "Cultural")


def _parse_event(raw: dict) -> dict | None:
    event_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not event_id or not name:
        return None
    embedded = raw.get("_embedded") or {}
    venue = (embedded.get("venues") or [{}])[0]
    attraction = (embedded.get("attractions") or [{}])[0]
    start = (raw.get("dates") or {}).get("start") or {}
    event_date, event_time = str(start.get("localDate") or ""), str(start.get("localTime") or "")
    try:
        event_day = date.fromisoformat(event_date)
        days = (event_day - date.today()).days
        dt = datetime.strptime(f"{event_date} {event_time[:5] or '00:00'}", "%Y-%m-%d %H:%M")
        label = dt.strftime("%b %d, %Y").replace(" 0", " ")
        if event_time:
            label += dt.strftime(" @ %I:%M %p").replace(" 0", " ")
    except (ValueError, TypeError):
        days, label = 999, event_date or "Date TBA"
    classification = (raw.get("classifications") or [{}])[0]
    images = [image for image in (raw.get("images") or []) if int(image.get("width") or 0) <= 1300]
    image = max(images, key=lambda value: int(value.get("width") or 0)).get("url", "") if images else ""
    price = (raw.get("priceRanges") or [{}])[0]
    minimum = price.get("min")
    price_label = f"from ${minimum:.0f}" if isinstance(minimum, (int, float)) and price.get("currency") == "USD" else ""
    city = str((venue.get("city") or {}).get("name") or "")
    state = str((venue.get("state") or {}).get("stateCode") or "")
    where = ", ".join(part for part in (city, state) if part)
    category = classification.get("segment") or {}
    genre = classification.get("genre") or {}
    subgenre = classification.get("subGenre") or {}
    return {
        "id": event_id, "name": name, "url": str(raw.get("url") or ""), "label": label, "days": days,
        "date": event_date, "venue": str(venue.get("name") or ""), "where": where, "img": image,
        "price": price_label, "segment": str(category.get("name") or ""),
        "genre": str(genre.get("name") or ""), "sub": str(subgenre.get("name") or ""),
        "type": str(raw.get("type") or ""), "subtype": str(raw.get("subType") or ""),
        "attraction": str(attraction.get("name") or ""),
        "desc": f"{venue.get('name', '')}, {where}. " + str(raw.get("info") or raw.get("pleaseNote") or "")[:400],
    }


def _request_events(key: str, params: dict, page_limit: int) -> list[dict]:
    global _LAST_REQUEST_AT
    found = []
    for page in range(page_limit):
        with _REQUEST_LOCK:
            wait = 0.5 - (time.monotonic() - _LAST_REQUEST_AT)
            if wait > 0:
                time.sleep(wait)
            _LAST_REQUEST_AT = time.monotonic()
        query = dict(params, apikey=key, sort="date,asc", size=200, page=page)
        request = Request(API_URL + "?" + urlencode(query), headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderCatalogError(f"Ticketmaster returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise ProviderCatalogError("Ticketmaster could not be reached or returned invalid data.") from None
        found.extend((payload.get("_embedded") or {}).get("events", []))
        total_pages = int((payload.get("page") or {}).get("totalPages") or 1)
        if page + 1 >= total_pages:
            break
    return found


def _fetch_ticketmaster(key: str, state_code: str | None, latitude: float | None,
                        longitude: float | None, radius: float) -> list[dict]:
    common = {"countryCode": "US"}
    if state_code:
        common["stateCode"] = state_code.upper()
        pages = 5
    else:
        common.update({"latlong": f"{latitude},{longitude}", "radius": radius, "unit": "miles"})
        pages = 1
    catalogs: dict[str, dict[str, dict]] = {"music": {}, "sports": {}, "festivals": {}}
    for classification, category in (("music", "music"), ("sports", "sports")):
        for raw in _request_events(key, dict(common, classificationName=classification), pages):
            event = _parse_event(raw)
            if event and event["days"] >= 0:
                catalogs[category][event["id"]] = event
    seen_festivals: set[str] = set()
    for keyword in ("festival", "fair", "party", "harvest", "parade"):
        for raw in _request_events(key, dict(common, keyword=keyword), pages):
            event = _parse_event(raw)
            if not event or event["days"] < 0 or event["id"] in seen_festivals or event["segment"].lower() == "sports":
                continue
            if keyword not in _norm(event["name"]).replace(" ", ""):
                continue
            seen_festivals.add(event["id"])
            catalogs["festivals"][event["id"]] = event

    result = []
    for category, events in catalogs.items():
        for event in events.values():
            genre = _genre_music(event) if category == "music" else _genre_sports(event) if category == "sports" else _genre_festival(event)
            media = {
                "title": event["name"], "sub": event["venue"], "year": event["date"][:4], "url": event["url"],
                "score": float(max(1, 100 - max(event["days"], 0))), "desc": event["desc"],
                "first_shown": "Live listing", "recent_shown": "Next: " + event["label"], "srcs": ["Ticketmaster"],
            }
            metadata = {"genre": genre, "online_v3": True, "buy_url": event["url"],
                        "buy_label": "Ticketmaster" + (f" · {event['price']}" if event["price"] else "")}
            if category == "music":
                text = _norm(" ".join((event["name"], event["genre"], event["sub"], event["type"], event["subtype"])))
                metadata.update({"music_genre": genre,
                                 "music_type": "Music Festivals" if "festival" in text else "Bands & Live Shows",
                                 "music_artist": event["attraction"]})
            result.append({"provider_id": event["id"], "category": category,
                           "payload": {"media": media, "event": {
                               "venue": event["venue"], "time": event["label"], "location": event["where"],
                               "purchase_url": event["url"], "poster": event["img"],
                           }, "metadata": metadata}})
    return result


def refresh_ticketmaster(db: Session, actor: Account, *, state_code: str | None,
                         latitude: float | None, longitude: float | None, radius: float) -> dict:
    scope = _scope(state_code, latitude, longitude)
    if not _REFRESH_LOCK.acquire(blocking=False):
        raise ProviderCatalogError("A Ticketmaster refresh is already in progress.")
    try:
        return _refresh_locked(db, actor, scope, state_code, latitude, longitude, radius)
    finally:
        _REFRESH_LOCK.release()


def _refresh_locked(db: Session, actor: Account, scope: str, state_code: str | None,
                    latitude: float | None, longitude: float | None, radius: float) -> dict:
    try:
        key = current_provider_secret(db, "ticketmaster")
    except ProviderSecretError as exc:
        raise ProviderCatalogError(str(exc)) from None
    if not key:
        raise ProviderCatalogError("Ticketmaster is not configured on the server yet.")
    # Complete provider fetch before changing persistent rows.
    fetched = _fetch_ticketmaster(key, state_code, latitude, longitude, radius)
    changed = {"music": 0, "sports": 0, "festivals": 0}
    prefix = scope + "|"
    cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
        ProviderCatalogItem.provider == "ticketmaster", ProviderCatalogItem.provider_id.like(prefix + "%"))) or 0)
    for entry in fetched:
        provider_id = prefix + entry["provider_id"]
        payload = dict(entry["payload"])
        payload["area_scope"] = scope
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        row = db.scalar(select(ProviderCatalogItem).where(
            ProviderCatalogItem.provider == "ticketmaster", ProviderCatalogItem.category == entry["category"],
            ProviderCatalogItem.provider_id == provider_id).with_for_update())
        if row is not None and row.fingerprint == fingerprint:
            continue
        cursor = max(cursor + 1, int(time.time() * 1000))
        if row is None:
            db.add(ProviderCatalogItem(provider="ticketmaster", category=entry["category"], provider_id=provider_id,
                                       payload=payload, fingerprint=fingerprint, updated_at_ms=cursor))
        else:
            row.payload = payload
            row.fingerprint = fingerprint
            row.updated_at_ms = cursor
        changed[entry["category"]] += 1
    db.add(AuditLog(actor_id=actor.id, action="provider_catalog.ticketmaster_refreshed",
                    entity_type="provider_catalog", entity_id=None,
                    details=f"{scope}: changed {changed['music']} music, {changed['sports']} sports, and {changed['festivals']} festival cards."))
    db.commit()
    latest = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(
        ProviderCatalogItem.provider == "ticketmaster", ProviderCatalogItem.provider_id.like(prefix + "%"))) or cursor)
    return {"scope": scope, "changed": changed, "cursor": latest, "fetched": len(fetched)}


def ticketmaster_delta(db: Session, scope: str, since: int = 0) -> dict:
    prefix = scope + "|"
    where = (ProviderCatalogItem.provider == "ticketmaster", ProviderCatalogItem.provider_id.like(prefix + "%"))
    rows = db.scalars(select(ProviderCatalogItem).where(*where, ProviderCatalogItem.updated_at_ms > max(0, since))
                      .order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    total = int(db.scalar(select(func.count()).select_from(ProviderCatalogItem).where(*where)) or 0)
    cursor = int(db.scalar(select(func.max(ProviderCatalogItem.updated_at_ms)).where(*where)) or 0)
    if since > cursor:
        rows = db.scalars(select(ProviderCatalogItem).where(*where).order_by(ProviderCatalogItem.updated_at_ms.asc())).all()
    catalogs = {"music": [], "sports": [], "festivals": []}
    for row in rows:
        catalogs[row.category].append(row.payload)
    return {"scope": scope, "available": bool(total), "cursor": cursor,
            "changed": {category: len(items) for category, items in catalogs.items()}, "catalogs": catalogs}
