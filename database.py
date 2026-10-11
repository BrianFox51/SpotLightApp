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
            purchase_url TEXT
        )
    """)
    
    # 4. Users (sign-up / sign-in; passwords are salted + hashed, never stored as text)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, display_name TEXT, salt TEXT, pw_hash TEXT,
            zip TEXT, city TEXT, state TEXT, lat REAL, lng REAL, created INTEGER
        )
    """)

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
            e_id = hashlib.sha1(f"{media_id}_{ev['venue']}_{ev['time']}".encode()).hexdigest()
            cursor.execute("""
                INSERT INTO local_events (event_id, media_id, venue_name, event_time, location_details, purchase_url)
                VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO NOTHING
            """, (e_id, media_id, ev['venue'], ev['time'], ev['location'], ev.get('purchase_url', '')))
            
    conn.commit()
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

def load_details(media_id):
    """Extracts biographical data lists and synchronized local timeline maps."""
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

def create_user(username, password, zip_code="", city="", state="", lat=None, lng=None):
    """Returns (ok, message)."""
    key = username.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    try:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (key,)).fetchone():
            return False, "That username is already taken."
        salt = os.urandom(16).hex()
        conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (key, username.strip(), salt, _hash(password, salt), zip_code, city, state, lat, lng, int(time.time())))
        conn.commit(); return True, "ok"
    finally: conn.close()

def verify_user(username, password):
    """Returns the user dict on success, else None."""
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    try:
        r = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        if r and _hash(password, r["salt"]) == r["pw_hash"]: return dict(r)
        return None
    finally: conn.close()

def dashboard_stats(city="", state="", username="__guest__"):
    """Counts for the dashboard, including this user's saved favorites."""
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    cats = dict(c.execute("SELECT category, COUNT(*) FROM media_items GROUP BY category").fetchall())
    def near(term):
        if not term: return 0
        return c.execute("SELECT COUNT(DISTINCT media_id) FROM local_events WHERE location_details LIKE ?", (f"%{term}%",)).fetchone()[0]
    out = {"cats": cats, "total": sum(cats.values()), "events": c.execute("SELECT COUNT(*) FROM local_events").fetchone()[0],
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

def prune_source(source, keep_ids):
    """Removes items that came from `source` (e.g. 'Community') but are no longer in the feed. Returns how many."""
    conn = sqlite3.connect(DB_PATH); keep = set(keep_ids)
    gone = [r[0] for r in conn.execute("SELECT id FROM media_items WHERE sources LIKE ?", (f'%"{source}"%',)).fetchall() if r[0] not in keep]
    conn.close()
    for i in gone: delete_item(i)
    return len(gone)


def prune_category_source(category, source, keep_ids):
    """Remove stale rows for one provider without touching other categories or sources."""
    conn = sqlite3.connect(DB_PATH); keep = set(keep_ids)
    gone = [r[0] for r in conn.execute("SELECT id FROM media_items WHERE category = ? AND sources LIKE ?",
                                      (category, f'%"{source}"%')).fetchall() if r[0] not in keep]
    conn.close()
    for item_id in gone: delete_item(item_id)
    return len(gone)


def prune_expired_watchmode(cutoff):
    """Delete Watchmode catalog rows older than the Free plan's 30-day cache window."""
    conn = sqlite3.connect(DB_PATH)
    gone = [row[0] for row in conn.execute(
        "SELECT id FROM media_items WHERE category IN ('streaming', 'movies', 'tv') AND sources LIKE ? AND last_updated < ?",
        ('%"Watchmode"%', cutoff)
    ).fetchall()]
    conn.close()
    for media_id_value in gone:
        delete_item(media_id_value)
    return len(gone)
