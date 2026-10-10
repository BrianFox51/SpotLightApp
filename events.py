"""Live nearby events (Ticketmaster Discovery API, free key) and ticket-vendor links. Config lives in ~/.spotlight/config.json."""
import os, json, time, datetime, urllib.parse
import database
from online import _json, _save, _slug, _q, _norm

CFG = os.path.join(database.HOME, "config.json")


def load_cfg():
    try:
        with open(CFG, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}


def save_cfg(d):
    with open(CFG, "w", encoding="utf-8") as f: json.dump(d, f, indent=1)


def vendor_links(query, cat=""):
    """Search links on established ticket vendors (used when an event has no direct ticket link yet)."""
    q = urllib.parse.quote_plus(query)
    if cat == "movies": return [("Fandango", "https://www.fandango.com/search?q=" + q), ("Showtimes", "https://www.google.com/search?q=" + q + "+showtimes")]
    v = [("Ticketmaster", "https://www.ticketmaster.com/search?q=" + q), ("SeatGeek", "https://seatgeek.com/search?search=" + q), ("StubHub", "https://www.stubhub.com/secure/search?q=" + q)]
    if cat == "festivals": v.insert(0, ("Eventbrite", "https://www.eventbrite.com/d/united-states/" + urllib.parse.quote(query.lower().replace(" ", "-")) + "/"))
    return v


SPORTS = {"baseball": "Baseball", "basketball": "Basketball", "football": "Football", "hockey": "Hockey", "soccer": "Soccer", "golf": "Golf", "tennis": "Tennis",
          "boxing": "MMA & Boxing", "martial arts": "MMA & Boxing", "mma": "MMA & Boxing", "wrestling": "Wrestling", "rodeo": "Rodeo", "motorsports": "Racing",
          "racing": "Racing", "poker": "Poker", "bowling": "Bowling", "esports": "Esports", "darts": "Darts", "billiards": "Pool & Billiards"}
FEST = [(("pumpkin", "harvest", "corn", "food", "taste", "wine", "beer", "apple", "chili", "bbq", "brat"), "Harvest & Food"), (("fair", "expo"), "County & State Fairs"),
        (("parade", "christmas", "holiday", "fireworks", "lights"), "Parades & Holidays"), (("film",), "Film Festivals"), (("art", "craft"), "Arts & Crafts"),
        (("car show", "auto", "motor"), "Car Shows"), (("renaissance", "faire", "fantasy", "comic"), "Renaissance & Fantasy"), (("music", "jazz", "blues", "rock", "fest"), "Music Festivals")]


def _music_genre(ev):
    """Map Ticketmaster classifications to the app's readable genre filters."""
    genre = _norm(ev["genre"] + " " + ev["sub"])
    if any(word in genre for word in ("hip hop", "rap")): return "Hip-Hop"
    if any(word in genre for word in ("r b", "rnb", "rhythm and blues", "soul")): return "R&B"
    if any(word in genre for word in ("electronic", "edm", "dance")): return "Electronic"
    if any(word in genre for word in ("latin", "salsa", "reggaeton")): return "Latin"
    if "country" in genre: return "Country"
    if "jazz" in genre: return "Jazz"
    if "pop" in genre: return "Pop"
    if any(word in genre for word in ("rock", "metal", "punk", "alternative", "indie")): return "Rock"
    return "Other"


def _music_type(ev):
    """Identify music festivals separately from artist and live-show events."""
    details = _norm(" ".join((ev["name"], ev["genre"], ev["sub"], ev["type"], ev["subtype"])))
    return "Music Festivals" if "festival" in details else "Bands & Live Shows"


def _sport_genre(ev):
    t = _norm(ev["genre"] + " " + ev["sub"] + " " + ev["name"])
    return next((v for k, v in SPORTS.items() if k in t), "Other")


def _fest_genre(ev):
    t = _norm(ev["name"])
    return next((g for keys, g in FEST if any(k in t for k in keys)), "Cultural")


def _parse(e):
    emb = e.get("_embedded") or {}; v = (emb.get("venues") or [{}])[0]; at = (emb.get("attractions") or [{}])[0]
    st = (e.get("dates") or {}).get("start") or {}; d, t = st.get("localDate", ""), st.get("localTime", "")
    try:
        dt = datetime.datetime.strptime(f"{d} {t[:5] or '00:00'}", "%Y-%m-%d %H:%M")
        label = dt.strftime("%b %d, %Y").replace(" 0", " ") + (dt.strftime(" @ %I:%M %p").replace(" 0", " ") if t else "")
        days = (dt.date() - datetime.date.today()).days
    except Exception: label, days = d or "Date TBA", 999
    c = (e.get("classifications") or [{}])[0]; imgs = [i for i in (e.get("images") or []) if i.get("width", 0) <= 1300]
    pr = (e.get("priceRanges") or [{}])[0]; city = (v.get("city") or {}).get("name", ""); state = (v.get("state") or {}).get("stateCode", "")
    where = ", ".join(x for x in (city, state) if x)
    return {"id": e.get("id"), "name": e.get("name", ""), "url": e.get("url", ""), "label": label, "days": days, "date": d, "venue": v.get("name", ""), "where": where,
            "img": max(imgs, key=lambda i: i.get("width", 0)).get("url", "") if imgs else "",
            "price": f"from ${pr['min']:.0f}" if pr.get("min") and pr.get("currency") == "USD" else "",
            "segment": (c.get("segment") or {}).get("name") or "", "genre": (c.get("genre") or {}).get("name") or "", "sub": (c.get("subGenre") or {}).get("name") or "",
            "type": e.get("type", ""), "subtype": e.get("subType", ""),
            "attraction": at.get("name", ""), "desc": f"{v.get('name', '')}, {where}. " + (e.get("info") or e.get("pleaseNote") or "")[:400]}


def _events(key, lat=None, lng=None, radius=75, state_code=None, **params):
    """Fetch event pages near a point or across one U.S. state.

    Ticketmaster limits deep paging to the first 1,000 matching events. State
    searches page through that available range; nearby searches keep one page
    so a local sync stays quick.
    """
    query = dict(apikey=key, sort="date,asc", size=200, **params)
    if state_code:
        query.update(countryCode="US", stateCode=state_code)
        page_limit = 5
    else:
        query.update(latlong=f"{lat},{lng}", radius=radius, unit="miles")
        page_limit = 1

    found = []
    for page in range(page_limit):
        time.sleep(0.5)  # Stay at or below Ticketmaster's documented 2 requests per second.
        response = _json("https://app.ticketmaster.com/discovery/v2/events.json?" + _q(**query, page=page))
        found.extend((response.get("_embedded") or {}).get("events", []))
        page_info = response.get("page") or {}
        if page + 1 >= page_info.get("totalPages", 1):
            break

    return [_parse(event) for event in found]


def sync(key, lat, lng, poster_dir, say=lambda s: None, radius=75, state_code=None):
    """Save nearby or statewide events and matching tour dates to the catalog.

    Supply ``state_code`` for a state-wide U.S. search. Otherwise, event
    listings use ``radius`` miles around ``lat`` and ``lng``. The return value
    contains title metadata and counts for music, sports, and festivals.
    """
    meta, n = {}, {"music": 0, "sports": 0, "festivals": 0}

    def find_events(search_radius, **filters):
        return _events(key, lat, lng, search_radius, state_code=state_code, **filters)

    def keep(cat, ev, genre, **extra_meta):
        item = {"title": ev["name"], "sub": ev["venue"], "year": ev["date"][:4], "url": ev["url"], "score": float(max(1, 100 - max(ev["days"], 0))), "desc": ev["desc"],
                "first_shown": "Live listing", "recent_shown": "Next: " + ev["label"], "srcs": ["Ticketmaster"]}
        database.save_media_item(cat, item, [], [{"venue": ev["venue"], "time": ev["label"], "location": ev["where"], "purchase_url": ev["url"]}])
        meta[(cat, ev["name"])] = {"genre": genre, "online_v3": True, "buy_url": ev["url"], "buy_label": "Ticketmaster" + (f" · {ev['price']}" if ev["price"] else ""), **extra_meta}
        p = os.path.join(poster_dir, _slug(ev["name"]) + ".jpg")
        if ev["img"] and not os.path.exists(p) and not os.path.exists(p[:-4] + ".png"):
            try: _save(ev["img"], p)
            except Exception: pass

    area = f"across {state_code}" if state_code else "nearby"
    say(f"Searching concerts and music {area}…")
    for ev in find_events(radius, classificationName="music"):
        if ev["days"] < 0:
            continue
        keep("music", ev, _music_genre(ev), music_genre=_music_genre(ev), music_type=_music_type(ev), music_artist=ev["attraction"]); n["music"] += 1
    say(f"Searching sports {area}…")
    for ev in find_events(radius, classificationName="sports"): keep("sports", ev, _sport_genre(ev)); n["sports"] += 1
    say("Searching festivals and fairs…"); seen = set()
    for kw in ("festival", "fair", "party", "harvest", "parade"):
        for ev in find_events(radius, keyword=kw):
            if ev["id"] in seen or ev["segment"].lower() == "sports" or kw not in _norm(ev["name"]).replace(" ", ""): continue
            seen.add(ev["id"]); keep("festivals", ev, _fest_genre(ev)); n["festivals"] += 1
    return {"meta": meta, **n}
