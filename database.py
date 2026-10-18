import os
import sqlite3
import hashlib
import json
import time

# This sets up a hidden folder on your PC to store your data safely
HOME = os.path.join(os.path.expanduser("~"), ".spotlight")
DB_PATH = os.path.join(HOME, "spotlight_storage_v2.db")
os.makedirs(HOME, exist_ok=True)

def init_db():
    """Builds a database structure to preserve charts, bios, and showtimes offline."""
    # Connects to the database file. If the file doesn't exist yet, it creates it!
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Core Chart Tracker (Holds songs, movies, games, and your personal notes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_items (
            id TEXT PRIMARY KEY,
            category TEXT,
            title TEXT,
            sub TEXT,
            year TEXT,
            url TEXT,
            score REAL,
            description TEXT,
            user_notes TEXT,
            sources TEXT,
            first_shown TEXT,
            recent_shown TEXT,
            last_updated INTEGER
        )
    """)
    
    # 2. Production Directory (Holds cast, crew, band members, and biographies)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cast_crew_directory (
            person_id TEXT PRIMARY KEY,
            media_id TEXT,
            name TEXT,
            role_type TEXT,
            biography TEXT,
            avatar_blob BLOB
        )
    """)
    
    # 3. Local Venues Ledger (Holds concert venues, theater times, and ticket links)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS local_events (
            event_id TEXT PRIMARY KEY,
            media_id TEXT,
            venue_name TEXT,
            event_time TEXT,
            location_details TEXT,
            purchase_url TEXT,
            area_scope TEXT NOT NULL DEFAULT ''
        )
    """)

    event_columns = {row[1] for row in cursor.execute("PRAGMA table_info(local_events)").fetchall()}
    if "area_scope" not in event_columns:
        cursor.execute("ALTER TABLE local_events ADD COLUMN area_scope TEXT NOT NULL DEFAULT ''")
    
    # 4. Users (sign-up / sign-in; passwords are salted + hashed, never stored as text)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, display_name TEXT, salt TEXT, pw_hash TEXT,
            zip TEXT, city TEXT, state TEXT, lat REAL, lng REAL, created INTEGER
        )
    """)

    # Add profile fields without breaking accounts created by earlier versions.
    user_columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    for name, declaration in (("email", "TEXT NOT NULL DEFAULT ''"), ("full_name", "TEXT NOT NULL DEFAULT ''"),
                              ("bio", "TEXT NOT NULL DEFAULT ''"), ("interests", "TEXT NOT NULL DEFAULT ''"),
                              ("website", "TEXT NOT NULL DEFAULT ''"), ("avatar_path", "TEXT NOT NULL DEFAULT ''")):
        if name not in user_columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {declaration}")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            username TEXT NOT NULL, media_id TEXT NOT NULL, created INTEGER NOT NULL,
            PRIMARY KEY (username, media_id)
        )
    """)

    # Save the changes and close the connection cleanly
    conn.commit()
    conn.close()

# Run this setup function automatically the moment this file is opened
init_db()
print("Vault Database successfully created and initialized!")


def save_media_item(cat, item, cast_list=None, event_list=None):
    """Atomically commits a media asset alongside its local events and cast directory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = int(time.time())
    
    # Generate an absolute unique key for this specific record
    media_id = hashlib.sha1(f"{cat}_{item['title']}_{item['sub']}".encode()).hexdigest()
    
    # Fetch existing notes if present to prevent accidental data overwrites
    cursor.execute("SELECT user_notes FROM media_items WHERE id = ?", (media_id,))
    row = cursor.fetchone()
    current_notes = row[0] if row else ""
    
    # Insert or update the core item details
    cursor.execute("""
        INSERT INTO media_items (id, category, title, sub, year, url, score, description, user_notes, sources, first_shown, recent_shown, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            year=excluded.year, score=excluded.score, description=excluded.description,
            sources=excluded.sources, first_shown=excluded.first_shown, recent_shown=excluded.recent_shown, last_updated=excluded.last_updated
    """, (media_id, cat, item['title'], item['sub'], item['year'], item['url'], item['score'], 
          item['desc'], current_notes, json.dumps(item.get('srcs', [])), item.get('first_shown', ''), item.get('recent_shown', ''), now))
    
    # Check if there is cast or crew data to save
    if cast_list:
        for member in cast_list:
            p_id = hashlib.sha1(f"{media_id}_{member['name']}".encode()).hexdigest()
            cursor.execute("""
                INSERT INTO cast_crew_directory (person_id, media_id, name, role_type, biography, avatar_blob)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(person_id) DO NOTHING
            """, (p_id, media_id, member['name'], member['role'], member['bio'], member.get('avatar', b'')))
            
    # Check if there are local tour dates or movie theater showtimes to save
    if event_list:
        for ev in event_list:
            area_scope = str(ev.get("area_scope") or "")
            e_id = hashlib.sha1(
                f"{media_id}_{ev['venue']}_{ev['time']}_{ev['location']}_{area_scope}".encode()
            ).hexdigest()
            cursor.execute("""
                INSERT INTO local_events
                    (event_id, media_id, venue_name, event_time, location_details, purchase_url, area_scope)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING
            """, (e_id, media_id, ev['venue'], ev['time'], ev['location'],
                  ev.get('purchase_url', ''), area_scope))
            
    conn.commit()
    conn.close()

def save_media_items(rows):
    """Write a catalog batch in one SQLite transaction to keep refresh responsive."""
    if not rows: return
    conn = sqlite3.connect(DB_PATH)
    try:
        for cat, item in rows:
            media_id = hashlib.sha1(f"{cat}_{item['title']}_{item['sub']}".encode()).hexdigest()
            existing = conn.execute("SELECT user_notes FROM media_items WHERE id = ?", (media_id,)).fetchone()
            notes = existing[0] if existing else ""
            conn.execute("""INSERT INTO media_items
                (id, category, title, sub, year, url, score, description, user_notes, sources, first_shown, recent_shown, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET url=excluded.url, year=excluded.year, score=excluded.score,
                description=excluded.description, sources=excluded.sources, first_shown=excluded.first_shown,
                recent_shown=excluded.recent_shown, last_updated=excluded.last_updated""",
                (media_id, cat, item["title"], item["sub"], item["year"], item["url"], item["score"], item["desc"],
                 notes, json.dumps(item.get("srcs", [])), item.get("first_shown", ""), item.get("recent_shown", ""), int(time.time())))
        conn.commit()
    finally:
        conn.close()

def clear_unfavorited_catalog_cache():
    """Clear cached catalog rows with no favorites or personal notes, preserving user data."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT id, user_notes FROM media_items").fetchall()
        favorite_ids = {row[0] for row in conn.execute("SELECT DISTINCT media_id FROM favorites")}
        removable = [media_id for media_id, notes in rows
                     if media_id not in favorite_ids and not str(notes or "").strip()]
        keep_count = len(rows) - len(removable)
        events_removed = credits_removed = 0
        for offset in range(0, len(removable), 500):
            batch = removable[offset:offset + 500]
            marks = ",".join("?" for _ in batch)
            events_removed += conn.execute(f"DELETE FROM local_events WHERE media_id IN ({marks})", batch).rowcount
            credits_removed += conn.execute(f"DELETE FROM cast_crew_directory WHERE media_id IN ({marks})", batch).rowcount
            conn.execute(f"DELETE FROM media_items WHERE id IN ({marks})", batch)
        conn.commit()
        return {"cards": len(removable), "events": events_removed, "credits": credits_removed, "kept": keep_count}
    finally:
        conn.close()

def load_local_catalog(cat):
    """Retrieves cached media structures directly out of offline system storage."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This allows us to access data by column names
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM media_items WHERE category = ? ORDER BY score DESC", (cat,))
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return items

def load_catalog_filter_data(username, media_ids):
    """Load favorite IDs and event locations for a category with batched database reads."""
    ids = list(dict.fromkeys(str(media_id) for media_id in media_ids if media_id))
    conn = sqlite3.connect(DB_PATH)
    try:
        favorite_ids = {row[0] for row in conn.execute(
            "SELECT media_id FROM favorites WHERE username = ?",
            (username or "__guest__",),
        )}
        events_by_media_id = {}
        for offset in range(0, len(ids), 800):
            batch = ids[offset:offset + 800]
            marks = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"SELECT media_id, area_scope, location_details FROM local_events WHERE media_id IN ({marks})",
                batch,
            )
            for media_id, area_scope, location_details in rows:
                events_by_media_id.setdefault(media_id, []).append({
                    "area_scope": area_scope,
                    "location_details": location_details,
                })
        return favorite_ids, events_by_media_id
    finally:
        conn.close()

def load_details(media_id):
    """Extract biography and event rows, including each event's cached search area."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM cast_crew_directory WHERE media_id = ?", (media_id,))
    cast = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM local_events WHERE media_id = ?", (media_id,))
    events = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return cast, events

def update_notes(media_id, notes):
    """Saves user custom notebook journal entries down to storage."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE media_items SET user_notes = ? WHERE id = ?", (notes, media_id))
    conn.commit()
    conn.close()



# ---------------- accounts + dashboard stats ----------------
def _hash(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt_hex), 200_000).hex()

def create_user(username, password, zip_code="", city="", state="", lat=None, lng=None, *, full_name="", email="", bio="", interests="", website="", avatar_path=""):
    """Returns (ok, message)."""
    key = username.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    try:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (key,)).fetchone():
            return False, "That username is already taken."
        if conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(?) AND email <> ''", (email.strip(),)).fetchone():
            return False, "That email is already linked to a Spotlight account."
        salt = os.urandom(16).hex()
        conn.execute("""INSERT INTO users (username, display_name, salt, pw_hash, zip, city, state, lat, lng, created,
                     email, full_name, bio, interests, website, avatar_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (key, full_name.strip() or username.strip(), salt, _hash(password, salt), zip_code, city, state, lat, lng, int(time.time()),
                      email.strip(), full_name.strip(), bio.strip(), interests.strip(), website.strip(), avatar_path.strip()))
        conn.commit(); return True, "ok"
    finally: conn.close()

def update_user_profile(username, fields):
    """Update the editable profile for a local account, enforcing unique email addresses."""
    key = username.strip().lower(); email = str(fields.get("email", "")).strip()
    conn = sqlite3.connect(DB_PATH)
    try:
        conflict = conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(?) AND username <> ? AND email <> ''", (email, key)).fetchone()
        if conflict: return False, "That email is already linked to another Spotlight account."
        conn.execute("""UPDATE users SET display_name=?, full_name=?, email=?, zip=?, city=?, state=?, lat=?, lng=?,
                     bio=?, interests=?, website=?, avatar_path=? WHERE username=?""",
                     (fields.get("full_name", "").strip() or key, fields.get("full_name", "").strip(), email,
                      fields.get("zip", ""), fields.get("city", ""), fields.get("state", ""), fields.get("lat"), fields.get("lng"),
                      fields.get("bio", "").strip(), fields.get("interests", "").strip(), fields.get("website", "").strip(),
                      fields.get("avatar_path", "").strip(), key))
        conn.commit(); return True, "Profile saved."
    finally: conn.close()

def username_for_recovery(email, zip_code):
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT username FROM users WHERE lower(email)=lower(?) AND zip=?", (email.strip(), zip_code.strip())).fetchone()
        return row[0] if row else None
    finally: conn.close()

def reset_password_locally(username, email, zip_code, new_password):
    """Reset a local account password after matching its email and ZIP on this device."""
    key = username.strip().lower(); conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT 1 FROM users WHERE username=? AND lower(email)=lower(?) AND zip=?", (key, email.strip(), zip_code.strip())).fetchone()
        if not row: return False
        salt = os.urandom(16).hex()
        conn.execute("UPDATE users SET salt=?, pw_hash=? WHERE username=?", (salt, _hash(new_password, salt), key))
        conn.commit(); return True
    finally: conn.close()

def verify_user(username, password):
    """Returns the user dict on success, else None."""
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        r = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        if r and _hash(password, r["salt"]) == r["pw_hash"]: return dict(r)
        return None
    finally: conn.close()

def get_user(username):
    """Load a local account profile by username."""
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
        return dict(row) if row else None
    finally: conn.close()

def dashboard_stats(city="", state="", username="__guest__"):
    """Counts for the dashboard, including this user's saved favorites."""
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    cats = dict(c.execute("SELECT category, COUNT(*) FROM media_items GROUP BY category").fetchall())
    # Keep the headline total aligned with the six category counts shown below it.
    displayed_categories = ("music", "movies", "tv", "games", "sports", "festivals")
    total = sum(cats.get(category, 0) for category in displayed_categories)
    def near(term):
        if not term: return 0
        return c.execute("SELECT COUNT(DISTINCT media_id) FROM local_events WHERE location_details LIKE ?", (f"%{term}%",)).fetchone()[0]
    out = {"cats": cats, "total": total, "events": c.execute("SELECT COUNT(*) FROM local_events").fetchone()[0],
           "near_city": near(city), "near_state": near(f", {state}" if state else ""),
           "favorites": c.execute("SELECT COUNT(*) FROM favorites WHERE username = ?", (username or "__guest__",)).fetchone()[0]}
    conn.close(); return out


def titles_for_person(name):
    """(category, title) pairs in your library that list this person in their cast / crew / band."""
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT DISTINCT m.category, m.title FROM cast_crew_directory c JOIN media_items m ON m.id = c.media_id WHERE c.name = ?", (name,)).fetchall()
    finally: conn.close()


def add_events(media_id, event_list):
    """Attach (or refresh) dated events / tour dates with real ticket links to an existing item."""
    conn = sqlite3.connect(DB_PATH)
    for ev in event_list:
        e_id = hashlib.sha1(f"{media_id}_{ev['venue']}_{ev['time']}".encode()).hexdigest()
        conn.execute("""INSERT INTO local_events (event_id, media_id, venue_name, event_time, location_details, purchase_url) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(event_id) DO UPDATE SET purchase_url=excluded.purchase_url, location_details=excluded.location_details""",
                     (e_id, media_id, ev["venue"], ev["time"], ev["location"], ev.get("purchase_url", "")))
    conn.commit(); conn.close()


def add_credits(media_id, people):
    """Full cast + crew for a title: people = [{'name', 'role'}], in billing order. Existing rows keep their position and biography."""
    conn = sqlite3.connect(DB_PATH)
    for p in people:
        pid = hashlib.sha1(f"{media_id}_{p['name']}".encode()).hexdigest()
        conn.execute("""INSERT INTO cast_crew_directory (person_id, media_id, name, role_type, biography, avatar_blob) VALUES (?, ?, ?, ?, '', x'')
                        ON CONFLICT(person_id) DO UPDATE SET role_type=excluded.role_type""", (pid, media_id, p["name"], p["role"]))
    conn.commit(); conn.close()


def media_id(cat, title, sub):
    return hashlib.sha1(f"{cat}_{title}_{sub}".encode()).hexdigest()

def is_favorite(username, item_id):
    """Check whether a catalog item is starred by this local Spotlight user."""
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT 1 FROM favorites WHERE username = ? AND media_id = ?", (username or "__guest__", item_id)).fetchone() is not None
    finally:
        conn.close()

def load_favorites(username):
    """Return this local account's favorited catalog items, newest favorite first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""SELECT m.* FROM favorites f
            JOIN media_items m ON m.id = f.media_id
            WHERE f.username = ? AND m.category IN ('music', 'movies', 'tv', 'games', 'sports', 'festivals')
            ORDER BY f.created DESC, m.title COLLATE NOCASE""", (username or "__guest__",))
        return [dict(row) for row in rows.fetchall()]
    finally:
        conn.close()

def set_favorite(username, item_id, favorite):
    """Add or remove one user's favorite without changing the catalog item."""
    conn = sqlite3.connect(DB_PATH)
    user_key = username or "__guest__"
    if favorite:
        conn.execute("INSERT OR IGNORE INTO favorites (username, media_id, created) VALUES (?, ?, ?)", (user_key, item_id, int(time.time())))
    else:
        conn.execute("DELETE FROM favorites WHERE username = ? AND media_id = ?", (user_key, item_id))
    conn.commit(); conn.close()

def delete_item(mid):
    conn = sqlite3.connect(DB_PATH)
    for t in ("media_items", "local_events", "cast_crew_directory"): conn.execute(f"DELETE FROM {t} WHERE " + ("id" if t == "media_items" else "media_id") + " = ?", (mid,))
    conn.execute("DELETE FROM favorites WHERE media_id = ?", (mid,))
    conn.commit(); conn.close()

def move_favorites(old_media_id, new_media_id):
    """Move every local account's favorite links when a catalog ID is migrated."""
    if not old_media_id or not new_media_id or old_media_id == new_media_id:
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute("""INSERT OR IGNORE INTO favorites (username, media_id, created)
            SELECT username, ?, created FROM favorites WHERE media_id = ?""", (new_media_id, old_media_id))
        moved = cursor.rowcount
        conn.execute("DELETE FROM favorites WHERE media_id = ?", (old_media_id,))
        conn.commit()
        return moved
    finally:
        conn.close()

def _prunable_provider_ids(conn, rows, source):
    """Return only un-favorited rows owned exclusively by this provider."""
    favorite_ids = {row[0] for row in conn.execute("SELECT DISTINCT media_id FROM favorites")}
    prunable = []
    for media_id_value, sources_json in rows:
        try:
            sources = json.loads(sources_json or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(sources, list) or source not in sources:
            continue
        if any(value != source for value in sources) or media_id_value in favorite_ids:
            continue
        prunable.append(media_id_value)
    return prunable

def _delete_catalog_rows(conn, media_ids):
    """Delete catalog rows and their dependent event/credit records in one transaction."""
    if not media_ids:
        return
    for offset in range(0, len(media_ids), 500):
        batch = media_ids[offset:offset + 500]
        marks = ",".join("?" for _ in batch)
        for table, column in (("local_events", "media_id"), ("cast_crew_directory", "media_id"), ("media_items", "id")):
            conn.execute(f"DELETE FROM {table} WHERE {column} IN ({marks})", batch)

def prune_source(source, keep_ids):
    """Remove stale provider-only rows; empty results are treated as inconclusive."""
    if not keep_ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        keep = set(keep_ids)
        rows = conn.execute("SELECT id, sources FROM media_items WHERE sources LIKE ?", (f'%"{source}"%',)).fetchall()
        candidates = [row for row in rows if row[0] not in keep]
        gone = _prunable_provider_ids(conn, candidates, source)
        _delete_catalog_rows(conn, gone)
        conn.commit()
        return len(gone)
    finally:
        conn.close()


def prune_category_source(category, source, keep_ids):
    """Remove stale provider-only rows; empty results are inconclusive, not a clear-all."""
    if not keep_ids:
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        keep = set(keep_ids)
        rows = conn.execute("SELECT id, sources FROM media_items WHERE category = ? AND sources LIKE ?",
                            (category, f'%"{source}"%')).fetchall()
        candidates = [row for row in rows if row[0] not in keep]
        gone = _prunable_provider_ids(conn, candidates, source)
        _delete_catalog_rows(conn, gone)
        conn.commit()
        return len(gone)
    finally:
        conn.close()


def prune_expired_watchmode(cutoff):
    """Delete expired Watchmode-only rows unless a local account has favorited them."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT id, sources FROM media_items WHERE category IN ('streaming', 'movies', 'tv') AND sources LIKE ? AND last_updated < ?",
            ('%"Watchmode"%', cutoff)
        ).fetchall()
        gone = _prunable_provider_ids(conn, rows, "Watchmode")
        _delete_catalog_rows(conn, gone)
        conn.commit()
        return len(gone)
    finally:
        conn.close()

def prune_expired_event_items(expired_ids):
    """Remove expired event-feed rows while retaining favorites and non-event sources."""
    if not expired_ids:
        return 0
    event_sources = {"Ticketmaster", "OhioFestivals.net"}
    expired_ids = list(dict.fromkeys(expired_ids))
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = []
        for offset in range(0, len(expired_ids), 500):
            batch = expired_ids[offset:offset + 500]
            marks = ",".join("?" for _ in batch)
            rows.extend(conn.execute(f"SELECT id, sources FROM media_items WHERE id IN ({marks})", batch).fetchall())
        favorite_ids = {row[0] for row in conn.execute("SELECT DISTINCT media_id FROM favorites")}
        gone = []
        for media_id_value, sources_json in rows:
            try:
                sources = json.loads(sources_json or "[]")
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(sources, list) or not sources or not set(sources).issubset(event_sources):
                continue
            if media_id_value not in favorite_ids:
                gone.append(media_id_value)
        _delete_catalog_rows(conn, gone)
        conn.commit()
        return len(gone)
    finally:
        conn.close()
