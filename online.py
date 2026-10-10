"""Spotlight online helpers (no API keys): artwork, video/audio previews and buy links from Apple's iTunes Search API (movies, TV, music)
and the Steam store (games), plus cast / artist biographies and photos from Wikipedia. Results are cached on disk; fetch() and person()
raise on network failure so the caller can simply retry next time."""
import os, re, json, urllib.request, urllib.parse

UA = {"User-Agent": "SpotlightApp/1.0 (desktop media dashboard; https://mythicmaskworks.com)"}


def _get(url, timeout=10, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or UA), timeout=timeout) as r: return r.read()
def _json(url, headers=None): return json.loads(_get(url, 10, headers).decode("utf-8", "replace"))
def _norm(t): return re.sub(r"[^a-z0-9]+", " ", str(t).lower()).strip()
def _slug(t): return re.sub(r"[^a-z0-9]+", "-", str(t).lower()).strip("-")
def _q(**kw): return urllib.parse.urlencode(kw)
def _save(url, path, timeout=60):
    data = _get(url, timeout); tmp = path + ".part"
    with open(tmp, "wb") as f: f.write(data)
    os.replace(tmp, path)
def _money(v):
    try: return f"${float(v):.2f}" if float(v) > 0 else ""
    except Exception: return ""
def _has(folder, slug, exts): return any(os.path.exists(os.path.join(folder, slug + e)) for e in exts)


def _best(rows, key, title, artist="", year=""):
    """Best exact/contains title match; for music the artist must match too (so you get the original, not a cover)."""
    n, best, top = _norm(title), None, 0
    for r in rows:
        rn = _norm(r.get(key, "")); s = 4 if rn == n else (1 if n and n in rn else 0)
        if not s: continue
        if artist:
            if _norm(artist) not in _norm(r.get("artistName", "")): continue
            s += 3
        if year and str(r.get("releaseDate", ""))[:4] == str(year): s += 2
        if s > top: best, top = r, s
    return best


def _itunes(media, entity, key, term, title, artist="", year="", attr=None):
    q = dict(term=term, media=media, entity=entity, limit=25, country="us")
    if attr: q["attribute"] = attr
    return _best(_json("https://itunes.apple.com/search?" + _q(**q))["results"], key, title, artist, year)


def _artist_preview(media, entity, artist):
    """Find one playable Apple preview credited to the requested artist."""
    artist_key = _norm(artist)
    if not artist_key:
        return None
    rows = _json("https://itunes.apple.com/search?" + _q(term=artist, media=media, entity=entity, limit=25, country="us"))["results"]
    return next((row for row in rows if row.get("previewUrl") and artist_key in _norm(row.get("artistName", ""))), None)


def fetch(cat, title, sub, year, poster_dir, video_dir, slug, tmdb_key="", backdrop_dir=None, people_dir=None, artist=""):
    """Download artwork and available previews (never overwriting files added by the user)."""
    out, poster_url, poster_alt, clip_url, audio_url, backdrop_url, credits, tm = {}, None, None, None, None, None, None, None
    if tmdb_key and cat in ("movies", "tv"):
        try: tm = tmdb_fetch(cat, title, year, tmdb_key)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403): raise
            out["tmdb_error"] = "TMDB rejected the key"
    if cat in ("movies", "tv", "music"):
        if cat == "movies": r = _itunes("movie", "movie", "trackName", title, title, "", year, "movieTerm") or _itunes("movie", "movie", "trackName", f"{title} {year}", title, "", year)
        elif cat == "tv": r = _itunes("tvShow", "tvSeason", "collectionName", title, title, "", "", "tvShowTerm")
        else:
            credited_artist = artist or sub
            r = _itunes("music", "song", "trackName", f"{title} {credited_artist}", title, credited_artist, "", "songTerm") or _itunes("music", "song", "trackName", title, title, credited_artist)
        if r:
            poster_url = (r.get("artworkUrl100") or "").replace("100x100bb", "600x600bb") or None
            if cat != "music": clip_url = r.get("previewUrl")
            ms = r.get("trackTimeMillis")
            if ms: out["runtime"] = f"{ms // 3600000}h {ms // 60000 % 60}m" if cat == "movies" else f"{ms // 60000}:{ms // 1000 % 60:02d}"
            out["rated"] = r.get("contentAdvisoryRating") or ""
            link = r.get("trackViewUrl") or r.get("collectionViewUrl")
            if link:
                buy = _money(r.get("trackHdPrice") or r.get("trackPrice") or r.get("collectionHdPrice") or r.get("collectionPrice"))
                rent = _money(r.get("trackHdRentalPrice") or r.get("trackRentalPrice"))
                out["buy_url"] = link
                out["buy_label"] = ("Apple Music" if cat == "music" else "Apple TV") + (f" · Buy {buy}" if buy else "") + (f" · Rent {rent}" if rent else "")
        if cat == "music":
            audio_url = (r or {}).get("previewUrl") or None
            mv = _itunes("musicVideo", "musicVideo", "trackName", f"{title} {credited_artist}", title, credited_artist)
            # For concert listings, the event title is rarely a song title. Fall back to
            # a preview credited to the performing artist in that case.
            mv = mv or _artist_preview("musicVideo", "musicVideo", credited_artist)
            clip_url = mv.get("previewUrl") if mv else None
            if not audio_url:
                song = _artist_preview("music", "song", credited_artist)
                audio_url = song.get("previewUrl") if song else None
    elif cat == "games":
        items = _json("https://store.steampowered.com/api/storesearch/?" + _q(term=title, cc="us", l="en")).get("items", [])
        r = next((i for i in items if _norm(i.get("name", "")) == _norm(title)), None)
        if r:
            aid = r["id"]; base = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/"
            poster_url, poster_alt = base + "library_600x900.jpg", base + "header.jpg"
            out["buy_url"], out["buy_label"] = f"https://store.steampowered.com/app/{aid}", "Steam"
            try:
                d = _json(f"https://store.steampowered.com/api/appdetails?" + _q(appids=aid, cc="us", l="en"))[str(aid)].get("data", {})
                mp4 = ((d.get("movies") or [{}])[0].get("mp4") or {}); clip_url = mp4.get("480") or mp4.get("max")
                backdrop_url = ((d.get("screenshots") or [{}])[0]).get("path_full") or backdrop_url
                price = (d.get("price_overview") or {}).get("final_formatted") or ("Free" if d.get("is_free") else "")
                out["buy_label"] = "Steam" + (f" · {price}" if price else "")
            except Exception: pass
    if tm:
        poster_url, backdrop_url, credits = tm["poster"] or poster_url, tm["backdrop"], tm["credits"]
        for k in ("runtime", "rated", "genres", "tmdb_score", "tmdb_url", "tmdb_id", "yt_id"):
            if tm.get(k): out[k] = tm[k]
    try:
        wk = wiki_find(title, (f"{sub} song",) if cat == "music" else _HINT.get(cat, ()))
    except Exception:
        if cat != "music":
            raise
        # A missing biography should not prevent the music preview lookup/cache from completing.
        wk = None
    if wk:
        out["about"], out["about_url"] = wk["about"][:2500], wk["url"]
        if not poster_url and wk["thumb"]: poster_url = wk["thumb"]
    if not out.get("about") and tm and tm.get("about"): out["about"] = tm["about"]
    if credits is None and cat in ("movies", "tv"):
        try: credits = wikidata_credits(title, year, cat)
        except Exception: credits = None
    if poster_url and not _has(poster_dir, slug, (".jpg", ".png")):
        for u in (poster_url, poster_alt):
            if not u: continue
            try: _save(u, os.path.join(poster_dir, slug + ".jpg")); break
            except Exception: continue
    if backdrop_dir:   # a still / screenshot for the player box: TMDB backdrop, Steam screenshot, else the trailer's own thumbnail
        os.makedirs(backdrop_dir, exist_ok=True); bp = os.path.join(backdrop_dir, slug + ".jpg")
        yt = out.get("yt_id"); cands = ([backdrop_url] if backdrop_url else []) + ([f"https://i.ytimg.com/vi/{yt}/maxresdefault.jpg", f"https://i.ytimg.com/vi/{yt}/hqdefault.jpg"] if yt else [])
        for u in ([] if os.path.exists(bp) else cands):
            try: _save(u, bp); break
            except Exception: continue
    if credits:
        merged = {}
        for c in credits:
            e = merged.setdefault(c["name"], {"name": c["name"], "roles": [], "photo": c.get("photo", "")})
            if c.get("role") and c["role"] not in e["roles"]: e["roles"].append(c["role"])
            e["photo"] = e["photo"] or c.get("photo", "")
        people = list(merged.values())[:60]
        if people_dir:
            import concurrent.futures
            def grab(e):
                p = os.path.join(people_dir, _slug(e["name"]) + ".jpg")
                if e["photo"] and not os.path.exists(p):
                    try: _save(e["photo"], p, 15)
                    except Exception: pass
            with concurrent.futures.ThreadPoolExecutor(6) as ex: list(ex.map(grab, people))
        out["credits"] = [{"name": e["name"], "role": " / ".join(e["roles"])} for e in people]
    if clip_url and not _has(video_dir, slug, (".mp4", ".mov", ".mkv", ".webm")):
        try: _save(clip_url, os.path.join(video_dir, slug + ".mp4"), 120)
        except Exception: pass
    if cat == "music":
        video_path = next((os.path.join(video_dir, slug + ext) for ext in (".mp4", ".mov", ".mkv", ".webm") if os.path.exists(os.path.join(video_dir, slug + ext))), "")
        audio_path = os.path.join(video_dir, slug + ".audio.m4a")
        if audio_url and not os.path.exists(audio_path):
            try: _save(audio_url, audio_path, 120)
            except Exception: pass
        out["music_video"] = video_path
        out["music_audio"] = audio_path if os.path.exists(audio_path) else ""
        out["music_media_v1"] = True
    return out


IMG = "https://image.tmdb.org/t/p/"
_CREW_ORDER = ("Director", "Creator", "Screenplay", "Writer", "Story", "Producer", "Executive Producer", "Original Music Composer", "Director of Photography", "Editor", "Production Design")


def _tmdb(path, key, **params):
    hdr = dict(UA)
    if len(key) > 40: hdr["Authorization"] = "Bearer " + key   # v4 read-access token
    else: params["api_key"] = key                              # v3 api key
    return _json("https://api.themoviedb.org/3" + path + "?" + _q(**params), hdr)


def tmdb_fetch(cat, title, year, key):
    """The Movie Database (free key): poster, backdrop, full cast + key crew, official trailer id, rating, runtime. None if no match."""
    kind = "movie" if cat == "movies" else "tv"; nm = "title" if kind == "movie" else "name"
    r = None
    for q in ([dict(query=title, year=year)] if year and kind == "movie" else []) + [dict(query=title)]:
        r = _best(_tmdb(f"/search/{kind}", key, **q).get("results", []), nm, title)
        if r: break
    if not r: return None
    d = _tmdb(f"/{kind}/{r['id']}", key, language="en-US", append_to_response="credits,videos,release_dates" if kind == "movie" else "aggregate_credits,videos,content_ratings")
    out = {"poster": IMG + "w500" + d["poster_path"] if d.get("poster_path") else None, "backdrop": IMG + "w1280" + d["backdrop_path"] if d.get("backdrop_path") else None,
           "about": " ".join(x for x in (d.get("tagline"), d.get("overview")) if x), "tmdb_id": d["id"], "tmdb_url": f"https://www.themoviedb.org/{kind}/{d['id']}",
           "genres": ", ".join(x["name"] for x in d.get("genres", []))}
    if d.get("vote_average"): out["tmdb_score"] = f"{d['vote_average']:.1f}/10"
    if kind == "movie" and d.get("runtime"): out["runtime"] = f"{d['runtime'] // 60}h {d['runtime'] % 60}m"
    if kind == "tv" and d.get("number_of_seasons"): out["runtime"] = f"{d['number_of_seasons']} season{'s' if d['number_of_seasons'] != 1 else ''}"
    if kind == "movie":
        us = next((x for x in (d.get("release_dates") or {}).get("results", []) if x.get("iso_3166_1") == "US"), {})
        out["rated"] = next((x["certification"] for x in us.get("release_dates", []) if x.get("certification")), "")
    else:
        out["rated"] = next((x["rating"] for x in (d.get("content_ratings") or {}).get("results", []) if x.get("iso_3166_1") == "US"), "")
    vids = [v for v in (d.get("videos") or {}).get("results", []) if v.get("site") == "YouTube"]
    vids.sort(key=lambda v: (v.get("type") != "Trailer", not v.get("official"), v.get("type") != "Teaser"))
    if vids: out["yt_id"] = vids[0]["key"]
    ph = lambda p: IMG + "w185" + p if p else ""
    if kind == "movie":
        cr = d.get("credits") or {}
        cast = [{"name": c["name"], "role": c.get("character") or "Cast", "photo": ph(c.get("profile_path"))} for c in cr.get("cast", [])[:40]]
        crew = [{"name": c["name"], "role": c["job"], "photo": ph(c.get("profile_path"))} for c in cr.get("crew", []) if c.get("job") in _CREW_ORDER]
    else:
        cr = d.get("aggregate_credits") or {}
        cast = [{"name": c["name"], "role": ((c.get("roles") or [{}])[0].get("character")) or "Cast", "photo": ph(c.get("profile_path"))} for c in cr.get("cast", [])[:40]]
        crew = [{"name": c["name"], "role": "Creator", "photo": ph(c.get("profile_path"))} for c in d.get("created_by", [])]
        crew += [{"name": c["name"], "role": ((c.get("jobs") or [{}])[0].get("job")), "photo": ph(c.get("profile_path"))} for c in cr.get("crew", []) if ((c.get("jobs") or [{}])[0].get("job")) in _CREW_ORDER]
    crew.sort(key=lambda c: _CREW_ORDER.index(c["role"]) if c["role"] in _CREW_ORDER else 99)
    out["credits"] = cast + crew[:16]
    return out


def tmdb_catalog(key):
    """Return the first page of current U.S. theatrical movies and on-air TV from TMDB."""
    catalogs = {}
    for cat, endpoint, genre_endpoint, title_key, date_key in (
        ("movies", "/movie/now_playing", "/genre/movie/list", "title", "release_date"),
        ("tv", "/tv/on_the_air", "/genre/tv/list", "name", "first_air_date"),
    ):
        genres = {genre["id"]: genre["name"] for genre in _tmdb(genre_endpoint, key, language="en-US").get("genres", [])}
        params = {"language": "en-US", "page": 1}
        if cat == "movies": params["region"] = "US"
        else: params["timezone"] = "America/New_York"
        rows = _tmdb(endpoint, key, **params).get("results", [])
        items = []
        for row in rows:
            title = (row.get(title_key) or "").strip()
            if not title:
                continue
            raw_genre = next((genres[gid] for gid in row.get("genre_ids", []) if gid in genres), "Other")
            genre = {"Science Fiction": "Sci-Fi", "Action & Adventure": "Action", "Documentary": "Docs"}.get(raw_genre, raw_genre)
            date = row.get(date_key) or ""
            items.append({
                "id": row.get("id"), "title": title,
                "year": date[:4], "date": date,
                "overview": row.get("overview") or "",
                "score": round(float(row.get("vote_average") or 0) * 10, 1),
                "genre": genre,
                "poster": IMG + "w500" + row["poster_path"] if row.get("poster_path") else "",
                "url": f"https://www.themoviedb.org/{'movie' if cat == 'movies' else 'tv'}/{row.get('id')}" if row.get("id") else "",
            })
        catalogs[cat] = items
    return catalogs


def wikidata_credits(title, year="", cat="movies"):
    """Key-free fallback: cast + key crew from Wikidata (less complete than TMDB). Returns a list of {name, role} or None."""
    S = "https://www.wikidata.org/w/api.php?format=json&"; words = ("film",) if cat == "movies" else ("television series", "tv series", "miniseries")
    rows = _json(S + _q(action="wbsearchentities", search=title, language="en", type="item", limit=10)).get("search", [])
    ok = [r for r in rows if any(w in r.get("description", "").lower() for w in words)]
    pick = next((r for r in ok if year and str(year) in r.get("description", "")), None) or (ok[0] if ok else None)
    if not pick: return None
    claims = _json(S + _q(action="wbgetentities", ids=pick["id"], props="claims"))["entities"][pick["id"]].get("claims", {})
    wanted, ids = [], set()
    for pid, role, lim in (("P161", "", 30), ("P57", "Director", 4), ("P58", "Screenplay", 4), ("P162", "Producer", 5), ("P86", "Composer", 3), ("P344", "Cinematography", 3), ("P1040", "Editor", 3)):
        for st in claims.get(pid, [])[:lim]:
            v = ((st.get("mainsnak") or {}).get("datavalue") or {}).get("value"); qid = v.get("id") if isinstance(v, dict) else None
            if not qid: continue
            ch = None
            if pid == "P161":
                q = (((st.get("qualifiers") or {}).get("P453") or [{}])[0].get("datavalue") or {}).get("value"); ch = q.get("id") if isinstance(q, dict) else None
            wanted.append((qid, role, ch)); ids.update(x for x in (qid, ch) if x)
    labels, ids = {}, list(ids)
    for i in range(0, len(ids), 50):
        ents = _json(S + _q(action="wbgetentities", ids="|".join(ids[i:i + 50]), props="labels", languages="en")).get("entities", {})
        labels.update({k: ((v.get("labels") or {}).get("en") or {}).get("value", "") for k, v in ents.items()})
    return [{"name": labels[q], "role": role or labels.get(ch) or "Cast"} for q, role, ch in wanted if labels.get(q)] or None


_HINT = {"movies": ("film",), "tv": ("TV series",), "games": ("video game",), "festivals": ("festival",)}


def wiki_find(title, hints=()):
    """Best-matching Wikipedia article for a title (film, series, game, team, festival): {about, url, thumb} or None."""
    base = _WIKI.replace("exlimit=1", "exlimit=5")
    for q in [f"{title} {h}".strip() for h in hints] + [title]:
        pages = (_json(base + "generator=search&gsrlimit=5&gsrsearch=" + urllib.parse.quote(q)).get("query") or {}).get("pages") or {}
        for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            ex = (p.get("extract") or "").strip()
            if ex and "may refer to" not in ex[:300] and _norm(title) in _norm(p.get("title", "")):
                return {"about": ex, "url": p.get("fullurl", ""), "thumb": (p.get("thumbnail") or {}).get("source")}
    return None


def cached_person(pdir, name):
    try:
        with open(os.path.join(pdir, _slug(name) + ".json"), encoding="utf-8") as f: return json.load(f)
    except Exception: return None


_WIKI = ("https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=extracts%7Cpageimages%7Cinfo&inprop=url"
         "&exintro=1&explaintext=1&exlimit=1&piprop=thumbnail&pithumbsize=600&")


def person(pdir, name):
    """Wikipedia intro + photo for a cast member / artist. Returns {'missing': True} when no confident match."""
    c = cached_person(pdir, name)
    if c is not None: return c
    def look(q, strict):
        pages = (_json(_WIKI + q).get("query") or {}).get("pages") or {}
        for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
            ex = (p.get("extract") or "").strip()
            if ex and "may refer to" not in ex[:300] and (not strict or _norm(name.split()[-1]) in _norm(p.get("title", ""))): return p
        return None
    p = look("titles=" + urllib.parse.quote(name), False) or look("generator=search&gsrlimit=3&gsrsearch=" + urllib.parse.quote(name), True)
    out = {"missing": True}
    if p:
        out = {"name": p["title"], "bio": p["extract"].strip(), "url": p.get("fullurl", ""), "photo": ""}
        th = (p.get("thumbnail") or {}).get("source"); path = os.path.join(pdir, _slug(name) + ".jpg")
        if os.path.exists(path): out["photo"] = path
        elif th:
            try: _save(th, path); out["photo"] = path
            except Exception: pass
    with open(os.path.join(pdir, _slug(name) + ".json"), "w", encoding="utf-8") as f: json.dump(out, f)
    return out
