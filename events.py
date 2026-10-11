"""Live nearby events (Ticketmaster Discovery API, free key) and ticket-vendor links. Config lives in ~/.spotlight/config.json."""
import os, json, time, datetime, urllib.parse, re
from html.parser import HTMLParser
import database
from online import _get, _json, _save, _slug, _q, _norm

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

OHIO_FESTIVAL_PAGES = {
    "https://ohiofestivals.net/ohio-festivals/": "festivals",
    "https://ohiofestivals.net/ohiofairs/": "fairs",
}


class _ScheduleParser(HTMLParser):
    """Collect short schedule lines and their inline links from the directory pages."""
    def __init__(self):
        super().__init__(); self.lines = []; self.headings = []; self.current = None
        self.depth = 0; self.href = None; self.anchor_text = ""; self.heading = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("h1", "h2", "h3"):
            self.heading = True
        if tag in ("p", "li"):
            if self.current is None:
                self.current = {"tokens": [], "anchors": []}; self.depth = 1
            else:
                self.depth += 1
        elif tag == "br" and self.current is not None:
            self.current["tokens"].append(("\n", None))
        elif tag == "a":
            self.href = attrs.get("href", ""); self.anchor_text = ""

    def handle_data(self, data):
        if self.current is not None:
            self.current["tokens"].append((data, self.href))
        if self.href:
            self.anchor_text += data
        if self.heading:
            self.headings.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            if self.current is not None and self.anchor_text.strip():
                self.current["anchors"].append((self.anchor_text.strip(), self.href))
            self.href = None; self.anchor_text = ""
        if tag in ("h1", "h2", "h3"):
            self.heading = False
        if tag in ("p", "li") and self.current is not None:
            self.depth -= 1
            if self.depth <= 0:
                tokens = self.current["tokens"]
                text = "".join(value for value, _url in tokens)
                for line in text.splitlines() or [text]:
                    line = line.strip()
                    if not line: continue
                    anchors = [(label, url) for label, url in self.current["anchors"] if label.casefold() in line.casefold()]
                    self.lines.append((line, anchors))
                self.current = None; self.depth = 0


def _schedule_entries(html, page_url, page_type, today=None):
    """Extract upcoming event facts and destination links; no page artwork or prose is copied."""
    today = today or datetime.date.today()
    parser = _ScheduleParser(); parser.feed(html)
    page_year = next((int(year) for text in parser.headings for year in re.findall(r"\b20\d{2}\b", text)), today.year)
    date_re = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?:\s*[-–]\s*(?:(\d{1,2})/)?(\d{1,2}))?(\*)?")
    entries = []
    for line, anchors in parser.lines:
        if any(term in line.casefold() for term in ("cancelled", "canceled", "discontinued")): continue
        match = date_re.search(line)
        if not match: continue
        month, day, end_month, end_day, unconfirmed = match.groups()
        try:
            start_date = datetime.date(page_year, int(month), int(day))
            finish_date = datetime.date(page_year, int(end_month or month), int(end_day or day))
        except ValueError:
            continue
        next_match = re.search(r"\bNEXT\s+(\d{1,2})/(\d{1,2})/(20\d{2})", line, re.I)
        if next_match:
            try:
                start_date = finish_date = datetime.date(int(next_match.group(3)), int(next_match.group(1)), int(next_match.group(2)))
            except ValueError:
                pass
        if finish_date < today: continue
        clean = line[match.end():].strip(" \t–—-:")
        event_anchor = next(((label, url) for label, url in anchors
                             if label and label.casefold() not in {"my review", "review", "more"}), ("", ""))
        title = event_anchor[0] or re.split(r"\s+[–—]\s+", clean, maxsplit=1)[0].strip(" –—")
        if not title or len(title) > 180: continue
        tail = clean
        if event_anchor[0] and event_anchor[0].casefold() in clean.casefold():
            index = clean.casefold().find(event_anchor[0].casefold())
            tail = clean[index + len(event_anchor[0]):]
            location = re.split(r"\s+[–—]\s+", tail.strip(" –—"), maxsplit=1)[0].strip(" ,–—")
        else:
            parts = re.split(r"\s+[–—]\s+", clean, maxsplit=1)
            location = parts[1].strip(" ,–—") if len(parts) > 1 else ""
        location = re.sub(r"\s+NEXT\s+.*$", "", location, flags=re.I).strip()
        if location.upper() in {"CANCELLED", "CANCELED", "DISCONTINUED"}: location = ""
        destination = urllib.parse.urljoin(page_url, event_anchor[1]) if event_anchor[1] else page_url
        title_norm = _norm(title)
        if any(term in title_norm for term in ("craft", "artisan", "vendor", "bazaar", "makers market", "art show", "flea market")):
            genre = "Arts & Crafts"
        elif any(term in title_norm for term in ("county fair", "state fair", "country fair", "street fair", "fairgrounds")):
            genre = "County & State Fairs"
        elif any(term in title_norm for term in ("car show", "auto show", "motor show")):
            genre = "Car Shows"
        elif any(term in title_norm for term in ("pumpkin", "harvest", "apple", "food", "wine", "beer", "chili", "bbq", "butter", "corn")):
            genre = "Harvest & Food"
        elif any(term in title_norm for term in ("parade", "christmas", "holiday", "fireworks", "lights")):
            genre = "Parades & Holidays"
        elif "film" in title_norm: genre = "Film Festivals"
        elif any(term in title_norm for term in ("renaissance", "ren fest", "renaissance faire", "comic con")): genre = "Renaissance & Fantasy"
        elif any(term in title_norm for term in ("music festival", "jazz festival", "blues festival")): genre = "Music Festivals"
        elif page_type == "fairs" and any(term in title_norm for term in ("expo", "trade show", "engine show")): genre = "County & State Fairs"
        else: genre = "Cultural"
        date_label = start_date.strftime("%b %d, %Y").replace(" 0", " ")
        if finish_date != start_date:
            date_label += " – " + (finish_date.strftime("%b %d, %Y") if finish_date.month != start_date.month else finish_date.strftime("%b %d")).replace(" 0", " ")
        if unconfirmed: date_label += " · date unconfirmed"
        entries.append({"title": title, "genre": genre, "year": str(start_date.year), "date": date_label,
                        "city": location, "url": destination, "source_url": page_url,
                        "page_type": page_type, "unconfirmed": bool(unconfirmed)})
    return entries


def sync_ohio_schedules(today=None):
    """Refresh upcoming Ohio festival/fair listings and link back to each source page."""
    all_entries = []
    for page_url, page_type in OHIO_FESTIVAL_PAGES.items():
        html = _get(page_url, timeout=20).decode("utf-8", "replace")
        all_entries.extend(_schedule_entries(html, page_url, page_type, today=today))
        time.sleep(0.5)
    keep_ids = []
    for entry in all_entries:
        location = f"{entry['city']}, OH" if entry["city"] else "Ohio"
        item = {"title": entry["title"], "sub": location, "year": entry["year"], "url": entry["url"], "score": 0,
                "desc": "Listed by OhioFestivals.net. Confirm dates and details with the event organizer.",
                "first_shown": "OhioFestivals.net schedule", "recent_shown": entry["date"], "srcs": ["OhioFestivals.net"]}
        database.save_media_item("festivals", item, [], [{"venue": entry["title"], "time": entry["date"],
            "location": location, "purchase_url": entry["url"]}])
        item_id = database.media_id("festivals", entry["title"], location); keep_ids.append(item_id)
        entry_meta = {"genre": entry["genre"], "event_website": entry["url"], "event_source_url": entry["source_url"],
                      "event_source_name": "Ohio Festivals · CC BY 4.0" if entry["page_type"] == "festivals" else "Ohio Festivals"}
        # Metadata is merged by the application after the worker returns.
        entry["meta"] = entry_meta
    removed = database.prune_category_source("festivals", "OhioFestivals.net", keep_ids)
    return {"entries": all_entries, "count": len(all_entries), "removed": removed}


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
