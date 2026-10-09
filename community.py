"""Community events: organizer submissions + a free curated feed (a plain events.json you host on GitHub). No server, no cost.
Flow: organizer fills the in-app form -> sends you the event (email / file) -> you review it with curator.py -> you publish events.json -> every SpotLight copy picks it up."""
import os, re, io, json, hashlib, datetime, urllib.parse, urllib.request
import database, events

DEFAULT_FEED_URL = ""        # EDIT: https://raw.githubusercontent.com/<you>/<repo>/main/events.json   (or set "community_feed_url" in ~/.spotlight/config.json)
DEFAULT_SUBMIT_EMAIL = ""    # EDIT: the address organizers should send submissions to      (or set "submit_email" in config.json)
TYPES = {"sports": ["Baseball", "Basketball", "Football", "Hockey", "Soccer", "Golf", "Tennis", "Racing", "MMA & Boxing", "Wrestling", "Rodeo", "Poker", "Bowling", "Pool & Billiards", "Darts", "Esports"],
         "festivals": ["Harvest & Food", "County & State Fairs", "Music Festivals", "Arts & Crafts", "Parades & Holidays", "Cultural", "Film Festivals", "Car Shows", "Renaissance & Fantasy"]}
CAT_NAMES = {"sports": "Sports & Events", "festivals": "Festivals & Fairs"}
MINE = os.path.join(database.HOME, "my_submissions.json"); CACHE = os.path.join(database.HOME, "community_feed.json")
PRIVATE = ("contact_email", "submitted_at")


def feed_url(): return events.load_cfg().get("community_feed_url") or DEFAULT_FEED_URL
def submit_email(): return events.load_cfg().get("submit_email") or DEFAULT_SUBMIT_EMAIL
def _url(u): return bool(re.match(r"^https?://[^\s]{3,290}$", u))
def _date(s):
    try: return datetime.date.fromisoformat(str(s).strip())
    except Exception: return None
def make_id(e): return hashlib.sha1(f"{e['title'].lower()}|{e['date']}|{e['venue'].lower()}|{e['city'].lower()}".encode()).hexdigest()[:12]
def public(e): return {k: v for k, v in e.items() if k not in PRIVATE}


def validate(f, allow_past=False, need_email=True):
    """Checks a submission (or a feed entry). Returns (clean_event, [problems]). Never trust a feed: everything is re-validated on import."""
    errs, e = [], {}
    def txt(k, label, mx, req=True):
        v = " ".join(str(f.get(k, "") or "").split())
        if req and not v: errs.append(f"{label} is required.")
        elif len(v) > mx: errs.append(f"{label} is too long (max {mx} characters)."); v = v[:mx]
        return v
    e["title"], e["venue"], e["city"], e["organizer"] = txt("title", "Event name", 80), txt("venue", "Venue", 80), txt("city", "City", 50), txt("organizer", "Organizer name", 60)
    e["address"], e["price"] = txt("address", "Address", 100, False), txt("price", "Price", 40, False)
    e["category"] = f.get("category") if f.get("category") in TYPES else ""
    if not e["category"]: errs.append("Choose a category.")
    e["type"] = f.get("type") if e["category"] and f.get("type") in TYPES[e["category"]] else ""
    if e["category"] and not e["type"]: errs.append("Choose an event type.")
    e["state"] = str(f.get("state", "")).strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", e["state"]): errs.append("State must be 2 letters, like OH.")
    d, x = _date(f.get("date")), (_date(f.get("end_date")) if str(f.get("end_date", "")).strip() else None)
    if d is None: errs.append("Start date must look like 2026-10-21.")
    elif d < datetime.date.today() and not allow_past: errs.append("The start date is in the past.")
    if str(f.get("end_date", "")).strip() and (x is None or (d and x < d)): errs.append("End date must look like 2026-10-24 and not be before the start.")
    e["date"], e["end_date"] = d.isoformat() if d else "", x.isoformat() if x else ""
    e["time"] = str(f.get("time", "")).strip()
    if e["time"] and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", e["time"]): errs.append("Start time must look like 19:30 (24-hour), or leave it blank.")
    e["ticket_url"] = str(f.get("ticket_url", "")).strip()
    if not _url(e["ticket_url"]): errs.append("Ticket / info link is required and must start with https:// (it lets us verify the event).")
    e["image_url"] = str(f.get("image_url", "") or "").strip()
    if e["image_url"] and not _url(e["image_url"]): errs.append("Image link must start with https:// (or leave it blank)."); e["image_url"] = ""
    e["description"] = str(f.get("description", "") or "").strip()[:1200]
    if len(e["description"]) < 20: errs.append("Description needs at least 20 characters.")
    e["contact_email"] = str(f.get("contact_email", "") or "").strip()[:120]
    if need_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e["contact_email"]): errs.append("A contact email is required (it is never shown publicly).")
    if not errs: e["id"] = make_id(e)
    return e, errs


def label(e):
    d = _date(e["date"]); x = _date(e.get("end_date"))
    s = f"{d:%b} {d.day}, {d.year}" if not x or x == d else f"{d:%b} {d.day} – {x:%b} {x.day}, {x.year}"
    return s + (" @ " + datetime.datetime.strptime(e["time"], "%H:%M").strftime("%I:%M %p").lstrip("0") if e.get("time") else "")


def _grab(url, path):
    """Downloads an organizer's image safely: images only, max 3 MB, re-encoded so nothing odd is stored."""
    from PIL import Image
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SpotlightApp/1.0"}), timeout=10) as r:
        if not r.headers.get("Content-Type", "").startswith("image/"): return
        data = r.read(3_000_001)
    if len(data) > 3_000_000: return
    im = Image.open(io.BytesIO(data)); im.verify(); Image.open(io.BytesIO(data)).convert("RGB").save(path, "JPEG", quality=88)


def save_events(evs, poster_dir, source="Community"):
    """Writes events into the library. Returns {(category, title): meta}."""
    meta, today = {}, datetime.date.today()
    for e in evs:
        days = (_date(e["date"]) - today).days; where = f"{e['city']}, {e['state']}"; loc = f"{e['address']}, {where}" if e.get("address") else where
        item = {"title": e["title"], "sub": e["venue"], "year": e["date"][:4], "url": e["ticket_url"], "score": float(max(1, 100 - max(days, 0))), "desc": e["description"][:200],
                "first_shown": "Community listing", "recent_shown": "Next: " + label(e), "srcs": [source]}
        database.save_media_item(e["category"], item, [], [{"venue": e["venue"], "time": label(e), "location": loc, "purchase_url": e["ticket_url"]}])
        meta[(e["category"], e["title"])] = {"genre": e["type"], "online_v3": True, "community": True, "about": e["description"] + (f"\n\nListed by {e['organizer']}" if e.get("organizer") else ""),
                                              "buy_url": e["ticket_url"], "buy_label": "Tickets / info" + (f" · {e['price']}" if e.get("price") else "")}
        p = os.path.join(poster_dir, re.sub(r"[^a-z0-9]+", "-", e["title"].lower()).strip("-") + ".jpg")
        if e.get("image_url") and not os.path.exists(p):
            try: _grab(e["image_url"], p)
            except Exception: pass
    return meta


def parse_feed(raw):
    data = json.loads(raw); items = data.get("events", []) if isinstance(data, dict) else data; out, ids, today = [], [], datetime.date.today()
    for f in items if isinstance(items, list) else []:
        if not isinstance(f, dict): continue
        e, errs = validate(f, allow_past=True, need_email=False)
        if errs: continue
        ids.append(e["id"])
        if (_date(e["end_date"]) or _date(e["date"])) >= today: out.append(e)   # ended events are dropped
    return out, ids


def sync(poster_dir):
    """Downloads the community feed and updates the library. None if no feed is configured."""
    url = feed_url()
    if not url: return None
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SpotlightApp/1.0"}), timeout=15) as r: raw = r.read(1_000_001)
    if len(raw) > 1_000_000: raise ValueError("feed is larger than 1 MB")
    evs, ids = parse_feed(raw.decode("utf-8", "replace")); meta = save_events(evs, poster_dir)
    gone = database.prune_source("Community", [database.media_id(e["category"], e["title"], e["venue"]) for e in evs])
    with open(CACHE, "w", encoding="utf-8") as f: json.dump({"ids": ids, "count": len(evs)}, f)
    return {"count": len(evs), "meta": meta, "pruned": gone}


def live_ids():
    try:
        with open(CACHE, encoding="utf-8") as f: return set(json.load(f).get("ids", []))
    except Exception: return set()


def load_mine():
    try:
        with open(MINE, encoding="utf-8") as f: return json.load(f)
    except Exception: return []
def _save_mine(L):
    with open(MINE, "w", encoding="utf-8") as f: json.dump(L, f, indent=1)
def add_mine(e): _save_mine([x for x in load_mine() if x.get("id") != e["id"]] + [{**e, "submitted_at": datetime.datetime.now().isoformat(timespec="seconds")}])
def remove_mine(eid):
    mine = load_mine()
    for x in mine:
        if x.get("id") == eid: database.delete_item(database.media_id(x["category"], x["title"], x["venue"]))
    _save_mine([x for x in mine if x.get("id") != eid])


def mailto(e):
    body = "Hi! Please list this event on SpotLight.\n\n" + json.dumps(e, separators=(",", ":"), ensure_ascii=False)
    q = urllib.parse.quote(body)
    if len(q) > 1800: q = urllib.parse.quote("Hi! Please list my event on SpotLight. (Paste the event data here: in SpotLight use 'Copy event data'.)")
    return f"mailto:{submit_email()}?subject={urllib.parse.quote('SpotLight event submission: ' + e['title'])}&body={q}"
