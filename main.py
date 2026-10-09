"""Spotlight - Local Media Dashboard. Install required packages from requirements.txt."""
import os, re, sys, json, math, time, queue, zlib, shutil, threading, subprocess, importlib.util, webbrowser, urllib.request, urllib.parse
import tkinter as tk
from tkinter import messagebox, filedialog
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageEnhance, ImageOps, ImageFont, ImageTk
import customtkinter as ctk
import database
import dashboard
import online
import events
import community
import promote
ctk.set_appearance_mode("Dark"); ctk.set_default_color_theme("blue")

BASE = os.path.dirname(os.path.abspath(__file__)); MEDIA = os.path.join(BASE, "media")
USER_MEDIA = os.path.join(database.HOME, "media")
LEGACY_META = os.path.join(BASE, "spotlight_meta.json")
META = os.path.join(database.HOME, "spotlight_meta.json")
POSTERS = os.path.join(USER_MEDIA, "posters")
BACKDROPS = os.path.join(USER_MEDIA, "backdrops")
PEOPLE = os.path.join(USER_MEDIA, "people")
VIDEOS = os.path.join(USER_MEDIA, "videos")
LEGACY_VIDEOS = os.path.join(MEDIA, "videos")
os.makedirs(os.path.join(MEDIA, "ambient"), exist_ok=True)
for _cache_dir in (POSTERS, BACKDROPS, PEOPLE, VIDEOS): os.makedirs(_cache_dir, exist_ok=True)


def _copy_legacy_cache(folder):
    """Copy old project-local image caches into user data without overwriting files."""
    source = os.path.join(MEDIA, folder)
    destination = os.path.join(USER_MEDIA, folder)
    if not os.path.isdir(source): return
    for current, subfolders, files in os.walk(source):
        relative = os.path.relpath(current, source)
        target_dir = destination if relative == "." else os.path.join(destination, relative)
        os.makedirs(target_dir, exist_ok=True)
        for filename in files:
            old_file = os.path.join(current, filename)
            new_file = os.path.join(target_dir, filename)
            if os.path.islink(old_file) or os.path.exists(new_file): continue
            try: shutil.copy2(old_file, new_file)
            except OSError: pass


for _cache_name in ("posters", "backdrops", "people"):
    _copy_legacy_cache(_cache_name)
BG, PANEL, CARD, HOVER = "#0b0b11", "#12121a", "#1a1a26", "#28283e"
NAV = [("music", "🎵", "Music Charts"), ("movies", "🎬", "Cinema Feeds"), ("tv", "📺", "TV Networks"), ("games", "🎮", "Gaming Hub"), ("sports", "🏆", "Sports & Events"), ("festivals", "🎪", "Festivals & Fairs")]
ACC = {"music": (214, 64, 190), "movies": (226, 72, 58), "tv": (36, 182, 196), "games": (84, 214, 108), "sports": (255, 140, 40), "festivals": (150, 110, 255)}
FXK = {"music": "music", "movies": "movies", "tv": "tv", "games": "games", "sports": "tv", "festivals": "music"}
TAG = {"music": "Trending tracks", "movies": "Now showing", "tv": "Streaming now", "games": "Playing now", "sports": "Upcoming events", "festivals": "Happening soon"}
UNIT = {"sports": "event", "festivals": "event"}
GENRES = {"music": [("Pop", "🎤"), ("Hip-Hop", "🎧"), ("Rock", "🎸"), ("Electronic", "🎛️"), ("R&B", "💜"), ("Country", "🤠"), ("Latin", "💃"), ("Jazz", "🎷")],
          "movies": [("Action", "💥"), ("Drama", "🎭"), ("Comedy", "😂"), ("Sci-Fi", "🚀"), ("Horror", "👻"), ("Thriller", "🔪"), ("Animation", "✏️"), ("Indie", "🎞️")],
          "tv": [("Drama", "🎭"), ("Comedy", "😂"), ("Sci-Fi", "🚀"), ("Reality", "📡"), ("Docs", "🌍"), ("Animation", "✏️")],
          "games": [("Action", "⚔️"), ("RPG", "🐉"), ("Strategy", "♟️"), ("Shooter", "🎯"), ("Indie", "🕹️"), ("Sports", "🏆")],
          "sports": [("Baseball", "⚾"), ("Basketball", "🏀"), ("Football", "🏈"), ("Hockey", "🏒"), ("Soccer", "⚽"), ("Golf", "⛳"), ("Tennis", "🎾"), ("Racing", "🏁"), ("MMA & Boxing", "🥊"),
                     ("Wrestling", "🤼"), ("Rodeo", "🤠"), ("Poker", "🃏"), ("Bowling", "🎳"), ("Pool & Billiards", "🎱"), ("Darts", "🎯"), ("Esports", "🎮")],
          "festivals": [("Harvest & Food", "🎃"), ("County & State Fairs", "🎡"), ("Music Festivals", "🎶"), ("Arts & Crafts", "🎨"), ("Parades & Holidays", "🎆"), ("Cultural", "🌍"), ("Film Festivals", "🎬"), ("Car Shows", "🚗"), ("Renaissance & Fantasy", "🏰")]}
# (cat, title, sub, year, score, desc, first_shown, recent_shown, genre, [(name, role, bio)], [(venue, time, location)])  -- demo data
SEED = [
 ("music", "Blinding Lights", "The Weeknd", "2020", 96.5, "Synthesized electronic synth-wave chart-topper.", "Nov 29, 2019", "On Tour Now", "Pop",
  [("Abel Tesfaye", "Lead Vocalist", "Grammy award winning alternative R&B visionary pioneer."), ("Max Martin", "Key Producer", "Legendary Swedish structural pop hit-maker.")],
  [("Columbus Nationwide Arena", "Oct 14, 2026 @ 7:30 PM", "Columbus, OH"), ("Cleveland Rocket Mortgage FieldHouse", "Oct 17, 2026 @ 8:00 PM", "Cleveland, OH")]),
 ("music", "As It Was", "Harry Styles", "2022", 93.1, "Synth-pop single about change and distance.", "Apr 1, 2022", "Chart staple", "Pop", [("Harry Styles", "Lead Vocalist", "Solo pop star and former One Direction member.")], []),
 ("music", "SICKO MODE", "Travis Scott", "2018", 91.4, "Multi-part trap anthem built on beat switches.", "Aug 3, 2018", "Festival staple", "Hip-Hop", [("Travis Scott", "Lead Artist", "Houston rapper, producer and festival headliner.")], []),
 ("music", "Bohemian Rhapsody", "Queen", "1975", 97.0, "Six-minute rock opera that broke every single-release rule.", "Oct 31, 1975", "Evergreen", "Rock", [("Freddie Mercury", "Lead Vocalist", "Queen's frontman and songwriter of the song.")], []),
 ("movies", "Everything Everywhere All at Once", "A24", "2022", 94.2, "An aging Chinese immigrant is swept up in an insane adventure across alternate realities.", "March 11, 2022", "Tonight at Multiplex", "Sci-Fi",
  [("Michelle Yeoh", "Evelyn Wang", "Academy Award winning martial arts and dramatic performance icon."), ("Ke Huy Quan", "Waymond Wang", "Acclaimed comeback cinema star and stunt coordinator.")],
  [("AMC Easton Town Center 30", "Tonight @ 7:00 PM & 9:45 PM", "Columbus, OH"), ("Gateway Film Center", "Tomorrow @ 4:30 PM", "High St, Columbus, OH")]),
 ("movies", "Mad Max: Fury Road", "Warner Bros.", "2015", 92.0, "A relentless desert chase and one of the great practical-effects action films.", "May 15, 2015", "Cult favorite", "Action", [("Charlize Theron", "Imperator Furiosa", "Oscar-winning actor and producer."), ("George Miller", "Director", "Creator of the Mad Max series.")], []),
 ("movies", "Get Out", "Universal", "2017", 91.0, "A social thriller that turns a weekend visit into a nightmare.", "Feb 24, 2017", "Streaming", "Horror", [("Jordan Peele", "Writer / Director", "Won the Oscar for Best Original Screenplay for this film.")], []),
 ("tv", "Breaking Bad", "AMC", "2008", 97.0, "A chemistry teacher turns to crime after a life-changing diagnosis.", "Jan 20, 2008", "Streaming", "Drama", [("Bryan Cranston", "Walter White", "Four-time Emmy winner for this role.")], []),
 ("tv", "Stranger Things", "Netflix", "2016", 90.0, "Kids in a 1980s Indiana town face government secrets and a parallel dimension.", "Jul 15, 2016", "Streaming", "Sci-Fi", [("Millie Bobby Brown", "Eleven", "Breakout star of the series.")], []),
 ("games", "Elden Ring", "FromSoftware", "2022", 96.0, "Open-world action RPG with world-building by George R. R. Martin.", "Feb 25, 2022", "Ongoing", "RPG", [("Hidetaka Miyazaki", "Director", "FromSoftware president and Soulsborne designer.")], []),
 ("games", "Hades", "Supergiant Games", "2020", 93.0, "A rogue-like dungeon crawler where dying is part of the story.", "Sep 17, 2020", "Ongoing", "Indie", [("Greg Kasavin", "Creative Director", "Writer and creative lead at Supergiant Games.")], []),
 # Demo rows for the new categories (real dates/tickets arrive with live event feeds)
 ("sports", "Ohio State Buckeyes Football", "Columbus, OH", "2026", 90.0, "Big Ten college football at Ohio Stadium.", "Fall season", "Home games this fall", "Football", [], []),
 ("sports", "Cleveland Guardians", "Cleveland, OH", "2026", 84.0, "Major League Baseball at Progressive Field.", "Spring to fall", "Season schedule", "Baseball", [], []),
 ("sports", "Cleveland Cavaliers", "Cleveland, OH", "2026", 83.0, "NBA basketball in downtown Cleveland.", "Fall to spring", "Season schedule", "Basketball", [], []),
 ("festivals", "Circleville Pumpkin Show", "Circleville, OH", "2026", 92.0, "Long-running October pumpkin festival with parades, food and the giant pumpkin weigh-off.", "Annual", "Third week of October", "Harvest & Food", [], []),
 ("festivals", "Ohio State Fair", "Columbus, OH", "2026", 91.0, "Annual state fair with rides, livestock shows, concerts and food.", "Annual", "Summer", "County & State Fairs", [], []),
]

def g(r, k, d=""):
    try: v = r[k]; return d if v is None else v
    except Exception: return d
def sub_of(it):
    for k in ("sub", "subtitle", "studio", "artist", "creator"):
        if g(it, k): return g(it, k)
    return ""
def slug(t): return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
def hexc(c, k=1.0): return "#%02x%02x%02x" % tuple(min(255, int(v * k)) for v in c)

class Meta:
    def __init__(s):
        # Preserve the existing project-local cache the first time the new
        # user-data location is used. Keep the original file as a local backup.
        if not os.path.exists(META) and os.path.isfile(LEGACY_META):
            try: shutil.copy2(LEGACY_META, META)
            except OSError: pass
        try:
            with open(META, encoding="utf-8") as metadata_file:
                s.d = json.load(metadata_file)
            if not isinstance(s.d, dict): s.d = {}
        except (OSError, ValueError): s.d = {}
    def get(s, cat, t): return s.d.get(f"{cat}|{t}", {})
    def put(s, cat, t, **kw): s.d.setdefault(f"{cat}|{t}", {}).update(kw); s.save()
    def save(s):
        os.makedirs(os.path.dirname(META), exist_ok=True)
        temporary = META + ".tmp"
        with open(temporary, "w", encoding="utf-8") as metadata_file:
            json.dump(s.d, metadata_file, indent=1)
        os.replace(temporary, META)

_ART = {}
def _font(size):
    for n in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try: return ImageFont.truetype(n, size)
        except OSError: pass
    return ImageFont.load_default()

_CREW = {"director", "writer", "screenplay", "producer", "composer", "cinematography", "cinematographer", "editor", "creator", "story", "music", "photography"}
def is_crew(role): return bool(_CREW & set(re.findall(r"[a-z]+", role.lower())))

def art(title, accent, size, initials=False):
    """Use cached poster art when available, or draw a title or initials card."""
    key = (title, accent, size, initials)
    if key in _ART: return _ART[key]
    w, h = size
    for ext in ("jpg", "png"):
        f = os.path.join(POSTERS, slug(title) + "." + ext)
        if os.path.exists(f): _ART[key] = ImageOps.fit(Image.open(f).convert("RGB"), size); return _ART[key]
    z = zlib.crc32(title.encode()) % 100 / 100.0
    y = np.linspace(0, 1, h)[:, None, None]; x = np.linspace(0, 1, w)[None, :, None]; a = np.array(accent) / 255.0
    img = a * (0.22 + 0.7 * y) * (0.65 + 0.35 * x) + np.array([z, 0.15, 1 - z]) * 0.16 * (1 - y)
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype("uint8")); d = ImageDraw.Draw(im)
    if initials:
        ini = "".join(p[0] for p in re.findall(r"[A-Za-z0-9]+", title)[:2]).upper() or "?"; d.text((w / 2, h / 2), ini, font=_font(int(h * 0.3)), fill=(255, 255, 255), anchor="mm")
    else:
        words = title.split() or [title]; lines, fs = [title], 10
        for fs in range(max(10, int(h * 0.15)), 7, -1):
            f = _font(fs); lines, cur = [], ""
            for wd in words:
                t = (cur + " " + wd).strip()
                if cur and d.textlength(t, font=f) > w * 0.84: lines.append(cur); cur = wd
                else: cur = t
            lines.append(cur)
            if len(lines) * fs * 1.25 <= h * 0.78 and max(d.textlength(l, font=f) for l in lines) <= w * 0.9: break
        y0 = h / 2 - (len(lines) - 1) * fs * 1.25 / 2
        for i, l in enumerate(lines): d.text((w / 2, y0 + i * fs * 1.25), l, font=_font(fs), fill=(255, 255, 255), anchor="mm")
    _ART[key] = im; return im

def still_frame(src, w, h, play):
    im = ImageEnhance.Brightness(ImageOps.fit(src, (w, h))).enhance(0.72)
    if play:
        d = ImageDraw.Draw(im); r = max(26, min(w, h) // 9); cx, cy = w // 2, h // 2
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0), outline=(255, 255, 255), width=3); d.polygon([(cx - r // 3, cy - r // 2), (cx - r // 3, cy + r // 2), (cx + r // 2, cy)], fill=(255, 255, 255))
    return im

def wave(im, t, accent):
    w, h = im.size; lay = Image.new("RGB", (w, h)); d = ImageDraw.Draw(lay); c = tuple(min(255, int(v * 0.5 + 130)) for v in accent)
    for amp, f, sp, wd in ((0.16, 3.0, 2.2, 3), (0.09, 7.0, -3.1, 2)):
        d.line([(x, h * 0.45 + h * amp * math.sin(x / w * f * 6.283 + t * sp) * (0.55 + 0.45 * math.sin(x / w * 5 + t))) for x in range(0, w, 4)], fill=c, width=wd)
    return ImageChops.add(ImageChops.add(im, lay.filter(ImageFilter.GaussianBlur(7))), lay)

def fx(kind, w, h, t, accent, cover=None):
    """Generated motion background: sweeping spotlight beams + a style per section. Used when no video file exists."""
    W, H = max(96, w // 3), max(48, h // 3)
    y = np.linspace(0, 1, H)[:, None]; x = np.linspace(0, 1, W)[None, :]; a = np.array(accent) / 255.0
    img = np.broadcast_to(((0.04 + 0.10 * y)[..., None] * (0.35 + a)), (H, W, 3)).copy()
    for ph, sp in ((0.0, 0.33), (2.2, 0.27), (4.1, 0.21)):
        src = 0.5 + 0.25 * math.sin(t * 0.13 + ph); line = src + (0.5 + 0.48 * math.sin(t * sp + ph) - src) * y
        img += (np.exp(-((x - line) / (0.02 + 0.13 * y)) ** 2) * 0.55 * (0.25 + 0.75 * y))[..., None] * (0.5 + a)
    if kind in ("music", "wave"):
        nb = 56; k = np.arange(nb); hts = 0.10 + 0.32 * (0.5 + 0.5 * np.sin(t * 3.1 + k * 0.63) * np.cos(t * 1.7 + k * 0.29))
        col = np.arange(W); mask = (np.arange(H)[:, None] / H > 1 - hts[col * nb // W][None, :]) & ((col % max(2, W // nb)) > 0)[None, :]
        img += mask[..., None] * a * 0.5
    elif kind == "games":
        gg = np.clip(y - 0.5, 1e-3, None); grid = ((np.sin(0.35 / gg - t * 3) > 0.96) | (np.abs(np.sin((x - 0.5) / gg * 9)) > 0.985)) & (y > 0.52)
        img += grid[..., None] * a * 0.9
    elif kind == "tv":
        img *= (0.86 + 0.14 * np.sin(np.arange(H)[:, None] * 2.2))[..., None]
        for i in range(3):
            cx, cy = 0.5 + 0.4 * math.sin(t * 0.2 + i * 2), 0.5 + 0.35 * math.cos(t * 0.17 + i * 3)
            img += (np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / 0.02)) * 0.35)[..., None] * a
    else: img += np.random.rand(H, W, 1) * 0.035
    img *= (1 - 0.6 * ((x - 0.5) ** 2 + (y - 0.5) ** 2 * 1.6))[..., None]
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype("uint8")).resize((w, h), Image.BILINEAR)
    if kind == "wave": im = wave(im, t, accent)
    if cover is not None:
        ah = int(h * 0.74); aw = int(ah * cover.width / cover.height); im.paste(cover.resize((aw, ah)), (int(w * 0.05), int((h - ah) / 2 - h * 0.03)))
    return im

class Stage(tk.Canvas):
    logo = None   # wordmark from the official logo, set by App.load_logos
    """Looping video (muted) or generated animation. One decoder thread at a time; switching items cancels the old one."""
    def __init__(self, master, mode, height):
        super().__init__(master, height=height, highlightthickness=0, bg="#08080c")
        self.mode, self.gen, self.video, self.failed, self.q = mode, 0, None, False, queue.Queue(maxsize=2)
        self.kind, self.accent, self.cover, self.lines, self.dim = "movies", ACC["movies"], None, ("", ""), 1.0
        self.t0, self.photo, self.size, self.status = time.time(), None, (0, 0), ("", "#888888")
        self.vinst = self.vp = self.vf = None; self.vlc_on = False; self.muted = True; self.still = self.on_click = self._sk = None
        self.bind("<Button-1>", lambda e: self.on_click and self.on_click())
        self.after(50, self.tick)
    def play(self, video, kind, accent, cover=None, lines=("", ""), dim=1.0, still=None):
        self.still, self._sk = still, None; self.gen += 1; self.failed = False; self.video = video if video and os.path.exists(video) else None
        self.kind, self.accent, self.cover, self.lines, self.dim = kind, accent, cover, lines, dim
        while not self.q.empty():
            try: self.q.get_nowait()
            except queue.Empty: break
        if self.mode == "theater":
            if self.video and self.vlc_start(self.video): return
            self.vlc_stop()
        if self.video: threading.Thread(target=self.decode, args=(self.gen, self.video), daemon=True).start()
    def vlc_start(self, path):
        """Optional: play with sound through VLC (needs python-vlc + VLC installed). Returns False so the silent built-in player is used instead."""
        try:
            import vlc
            if self.vinst is None: self.vinst = vlc.Instance("--quiet", "--no-video-title-show")
            if self.vf is None: self.vf = tk.Frame(self, bg="black")
            self.vf.place(x=0, y=0, relwidth=1, relheight=1); self.vf.update_idletasks()
            if self.vp is None: self.vp = self.vinst.media_player_new()
            self.vp.stop()
            if sys.platform.startswith("win"): self.vp.set_hwnd(self.vf.winfo_id())
            elif sys.platform == "darwin": self.vp.set_nsobject(self.vf.winfo_id())
            else: self.vp.set_xwindow(self.vf.winfo_id())
            md = self.vinst.media_new(path); md.add_option(":input-repeat=65535"); self.vp.set_media(md); self.vp.audio_set_mute(self.muted); self.vp.play()
            self.after(600, lambda: self.vp and self.vp.audio_set_mute(self.muted)); self.vlc_on = True; return True
        except Exception:
            self.vlc_stop(); return False
    def vlc_stop(self):
        try:
            if self.vp is not None: self.vp.stop()
        except Exception: pass
        if self.vf is not None: self.vf.place_forget()
        self.vlc_on = False
    def toggle_mute(self):
        self.muted = not self.muted
        try: self.vp.audio_set_mute(self.muted)
        except Exception: pass
        return self.muted
    def decode(self, gen, path):
        try:
            import imageio.v2 as iio
            while gen == self.gen:
                r = iio.get_reader(path); dt = 1.0 / (r.get_meta_data().get("fps") or 24); nxt = time.time()
                for f in r:
                    if gen != self.gen: break
                    w, h = self.size
                    if w < 20: time.sleep(0.05); continue
                    im = ImageOps.fit(Image.fromarray(f), (w, h))
                    if self.dim < 1: im = ImageEnhance.Brightness(im).enhance(self.dim)
                    while gen == self.gen:
                        try: self.q.put((gen, im), timeout=0.5); break
                        except queue.Full: pass
                    nxt += dt; time.sleep(max(0, nxt - time.time()))
                r.close()
        except Exception:
            if gen == self.gen: self.failed = True
    def tick(self):
        if self.vlc_on: self.after(250, self.tick); return
        w, h = self.winfo_width(), self.winfo_height(); self.size = (w, h); im = None
        if w > 20 and h > 20:
            if self.video and not self.failed:
                try:
                    gg, f = self.q.get_nowait()
                    if gg == self.gen: im = f
                except queue.Empty: pass
            elif self.still is not None:
                if self._sk != (w, h, self.gen): self._sk = (w, h, self.gen); im = still_frame(self.still, w, h, bool(self.on_click))
            else:
                im = fx(self.kind, w, h, time.time() - self.t0, self.accent, self.cover)
                if self.dim < 1: im = ImageEnhance.Brightness(im).enhance(self.dim)
            if im is not None:
                self.photo = ImageTk.PhotoImage(im); self.delete("all"); self.create_image(0, 0, image=self.photo, anchor="nw"); self.overlay(w, h)
        self.after(45, self.tick)
    def overlay(self, w, h):
        def txt(x, y, s, size, col="white", anc="nw", bold=True):
            f = ("Segoe UI", size, "bold" if bold else "normal")
            self.create_text(x + 2, y + 2, text=s, font=f, fill="#000000", anchor=anc); self.create_text(x, y, text=s, font=f, fill=col, anchor=anc)
        if self.mode == "hero":
            (self.create_image(22, 8, image=Stage.logo, anchor="nw") if Stage.logo else txt(24, 12, "SPOTLIGHT", 15)); txt(w - 20, 14, self.status[0], 11, self.status[1], "ne", False)
            txt(24, h - 62, self.lines[0], 30); txt(26, h - 16, self.lines[1], 12, "#dddddd", "sw", False)
        else:
            n = len(self.lines[0]); txt(24, h - 74, self.lines[0], 24 if n <= 22 else 18 if n <= 34 else 14); txt(26, h - 16, self.lines[1], 12, "#dddddd", "sw", False)

class Tip:
    """Hover tooltip drawn as a plain label inside the main window (no extra OS windows, so no blank !toplevel boxes)."""
    def __init__(s, w, text):
        s.w, s.text, s.lbl, s.job = w, text, None, None
        w.bind("<Enter>", s.schedule, add="+"); w.bind("<Leave>", s.hide, add="+"); w.bind("<Button-1>", s.hide, add="+")
    def schedule(s, e=None):
        if s.job is None and s.lbl is None: s.job = s.w.after(300, s.show)
    def show(s):
        s.job = None
        if s.lbl is not None or not s.w.winfo_exists(): return
        root = s.w.winfo_toplevel()
        s.lbl = tk.Label(root, text=s.text, bg="#000000", fg="white", font=("Segoe UI", 12, "bold"), padx=12, pady=6)
        s.lbl.place(x=s.w.winfo_rootx() - root.winfo_rootx() + s.w.winfo_width() + 10, y=s.w.winfo_rooty() - root.winfo_rooty() + s.w.winfo_height() // 2 - 16); s.lbl.lift()
    def hide(s, e=None):
        if s.job is not None:
            try: s.w.after_cancel(s.job)
            except Exception: pass
            s.job = None
        if s.lbl is not None:
            try: s.lbl.destroy()
            except Exception: pass
            s.lbl = None

def bind_all(w, fn):
    w.bind("<Button-1>", fn, add="+")
    for c in w.winfo_children(): bind_all(c, fn)

class App(ctk.CTk):
    def __init__(self):
        super().__init__(); self.title("Spotlight - Local Media Dashboard"); self.geometry("1440x880"); self.minsize(1100, 700); self.configure(fg_color=BG)
        self.meta, self.cat, self.genre, self.items, self.sel, self.imgs, self.cards, self.online, self._rs = Meta(), "music", None, [], None, [], {}, None, None
        self.uiq, self.sel_cat, self.pinned, self._hj, self._bio = queue.Queue(), None, False, None, None
        self.cast_all = self._tproc = None
        self.load_logos(); self.after(300, self.set_icon)
        self.seed(); self.build(); self.start_sentinel(); self.poll_status(); self.poll_ui(); self.bind("<Configure>", self.on_resize); self.home(); self.gate = dashboard.Gate(self, BASE); self.after(3000, self.sync_community)

    # ---------- data ----------
    def seed(self):
        if self.meta.d.get("_seeded_v3"): return
        have = {c: {g(i, "title") for i in database.load_local_catalog(c)} for c in ACC}
        for cat, title, sub, year, score, desc, first, recent, genre, cast, ev in SEED:
            try:
                if title not in have[cat]:
                    database.save_media_item(cat, {"title": title, "sub": sub, "year": year, "url": "", "score": score, "desc": desc, "first_shown": first, "recent_shown": recent, "srcs": ["Demo"]},
                                             [{"name": n, "role": r, "bio": b} for n, r, b in cast], [{"venue": v, "time": t, "location": l, "purchase_url": ""} for v, t, l in ev])
            except Exception as e: print("seed skipped:", title, e)
            self.meta.d.setdefault(f"{cat}|{title}", {}).setdefault("genre", genre)
        self.meta.d["_seeded_v3"] = True; self.meta.save()

    def genre_of(self, it): return self.meta.get(self.cat, g(it, "title")).get("genre", "Other")

    # ---------- layout ----------
    def build(self):
        self.hero = Stage(self, "hero", 150); self.hero.pack(fill="x")
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0); body.pack(fill="both", expand=True)
        rail = ctk.CTkFrame(body, width=84, fg_color=PANEL, corner_radius=0); rail.pack(side="left", fill="y"); rail.pack_propagate(False)
        self.navbtn = {}
        hb = ctk.CTkButton(rail, text="🏠", width=60, height=60, corner_radius=16, font=("Segoe UI Emoji", 28), fg_color="transparent", hover_color=HOVER, command=lambda: self.gate.show_dashboard())
        hb.pack(pady=(18, 4), padx=12); Tip(hb, "Dashboard")
        for key, ico, name in NAV:
            b = ctk.CTkButton(rail, text=ico, width=60, height=60, corner_radius=16, font=("Segoe UI Emoji", 28), fg_color="transparent", hover_color=HOVER, command=lambda k=key: self.click_cat(k))
            b.pack(pady=(18, 4), padx=12); self.navbtn[key] = b; b.bind("<Enter>", lambda e, k=key: self.hover_open(k), add="+"); b.bind("<Leave>", self.hover_leave, add="+")
        pb = ctk.CTkButton(rail, text="📣", width=60, height=60, corner_radius=16, font=("Segoe UI Emoji", 28), fg_color="transparent", hover_color=HOVER, command=self.open_promote)
        pb.pack(pady=(18, 4), padx=12); Tip(pb, "Promote your event")
        self.feed = ctk.CTkFrame(body, width=410, fg_color=PANEL, corner_radius=0); self.feed.pack(side="left", fill="y", padx=(2, 2)); self.feed.pack_propagate(False)
        top = ctk.CTkFrame(self.feed, fg_color="transparent"); top.pack(fill="x", padx=12, pady=(14, 6))
        self.back = ctk.CTkButton(top, text="‹", width=38, height=38, font=("Segoe UI", 24, "bold"), fg_color=CARD, hover_color=HOVER, command=self.show_genres)
        self.feed_title = ctk.CTkLabel(top, text="", font=("Segoe UI", 24, "bold"), anchor="w"); self.feed_title.pack(side="left", padx=8)
        self.list = ctk.CTkScrollableFrame(self.feed, fg_color="transparent"); self.list.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.insp = ctk.CTkScrollableFrame(body, fg_color=BG, corner_radius=0); self.insp.pack(side="left", fill="both", expand=True); self.insp_box = self.insp._parent_frame; self.feed.pack_forget(); self.feed.bind("<Leave>", self.hover_leave, add="+")
        p = self.insp
        hdr = ctk.CTkFrame(p, fg_color="transparent"); hdr.pack(fill="x", padx=18, pady=(14, 8))
        self.poster = ctk.CTkLabel(hdr, text=""); self.theater = Stage(hdr, "theater", 380); self.theater.pack(side="right", fill="both", expand=True)
        bar = ctk.CTkFrame(p, fg_color="transparent"); bar.pack(fill="x", padx=18)
        self.find_btn = ctk.CTkButton(bar, text="▶ Find on YouTube", width=140, fg_color=CARD, hover_color=HOVER, command=self.find_online)
        self.auto_var = ctk.BooleanVar(value=bool(events.load_cfg().get("auto_trailer")))
        ctk.CTkSwitch(bar, text="Auto-open trailer", variable=self.auto_var, command=lambda: events.save_cfg({**events.load_cfg(), "auto_trailer": self.auto_var.get()})).pack(side="right", padx=8)
        self.buy_btn = ctk.CTkButton(bar, text="", fg_color="#1E7A34", hover_color="#27a046", command=self.open_buy)
        self.trailer_btn = ctk.CTkButton(bar, text="▶  Play trailer", fg_color="#9b1c1c", hover_color="#c42a2a", command=self.play_trailer)
        self.mute_btn = ctk.CTkButton(bar, text="🔇  Sound off", fg_color=CARD, hover_color=HOVER, command=self.toggle_sound)
        self.title = ctk.CTkLabel(p, text="Pick a genre, then a title", font=("Segoe UI", 34, "bold"), anchor="w"); self.title.pack(fill="x", padx=20, pady=(14, 0))
        self.meta_lbl = ctk.CTkLabel(p, text="", font=("Segoe UI", 14), text_color="#9aa0b5", anchor="w"); self.meta_lbl.pack(fill="x", padx=20)
        self.desc = ctk.CTkLabel(p, text="", font=("Segoe UI", 16), text_color="#c8ccd8", justify="left", anchor="w", wraplength=800); self.desc.pack(fill="x", padx=20, pady=10)
        self.promo = self.make_promo(p); self.promo.pack(fill="x", padx=20, pady=10); self.detail = ctk.CTkFrame(p, fg_color="transparent")
        self.cast_row = self.section("👥  Cast & Crew"); self.ev_box = self.section("📍  Local Venues & Showtimes")
        self.about_box = self.section("📖  About"); nb = self.section("📝  Notes"); self.notes = ctk.CTkTextbox(nb, height=110, fg_color=CARD); self.notes.pack(fill="x", pady=4)
        ctk.CTkButton(nb, text="Save notes", command=self.save_notes).pack(anchor="e", pady=4)
    def section(self, label):
        ctk.CTkLabel(self.detail, text=label, font=("Segoe UI", 20, "bold"), anchor="w").pack(fill="x", padx=20, pady=(22, 6))
        f = ctk.CTkFrame(self.detail, fg_color="transparent"); f.pack(fill="x", padx=20); return f
    def on_resize(self, e=None):
        if self._rs: self.after_cancel(self._rs)
        def go():
            iw = self.insp.winfo_width()
            if iw > 200: self.theater.configure(height=140 if self.sel is None else int(min(max(iw * 0.42, 300), 500))); self.desc.configure(wraplength=max(300, iw - 80))
        self._rs = self.after(150, go)

    def load_logos(self):
        self.logo_pil = dashboard.load_logo(BASE); Stage.logo = None
        if self.logo_pil is not None:
            wm = self.logo_pil.crop(dashboard.WORDMARK); Stage.logo = ImageTk.PhotoImage(wm.resize((190, int(190 * wm.height / wm.width)), Image.LANCZOS))
    def set_icon(self):
        if self.logo_pil is None: return
        try:
            p = os.path.join(MEDIA, "spotlight.ico")
            if not os.path.exists(p):
                lg = dashboard.trim_logo(self.logo_pil); side = max(lg.size); cv = Image.new("RGBA", (side, side), (0, 0, 0, 0)); cv.paste(lg, ((side - lg.width) // 2, (side - lg.height) // 2))
                cv.save(p, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
            self.iconbitmap(p)
        except Exception: pass
    def make_promo(self, p):
        f = ctk.CTkFrame(p, fg_color="transparent"); self._promo_imgs = []; lg = dashboard.trim_logo(self.logo_pil)
        if lg is not None: ci = ctk.CTkImage(lg, size=(280, int(280 * lg.height / lg.width))); self._promo_imgs.append(ci); ctk.CTkLabel(f, text="", image=ci).pack(pady=(6, 4))
        path = dashboard.find_banner(BASE)
        if path:
            im = Image.open(path).convert("RGB"); ci = ctk.CTkImage(im, size=(260, int(260 * im.height / im.width))); self._promo_imgs.append(ci); ctk.CTkLabel(f, text="", image=ci).pack(pady=(10, 0))
        ctk.CTkButton(f, text="mythicmaskworks.com   ·   free app", fg_color="transparent", hover_color=HOVER, text_color="#c9a45c", font=("Segoe UI", 14, "bold"), command=lambda: webbrowser.open(dashboard.SITE)).pack(pady=4)
        return f
    def show_promo(self, on):
        if on: self.detail.pack_forget(); self.promo.pack(fill="x", padx=20, pady=10)
        else: self.promo.pack_forget(); self.detail.pack(fill="x")
        self.on_resize()

    # ---------- navigation ----------
    def mark_nav(self, cat):
        for k, b in self.navbtn.items(): b.configure(fg_color=hexc(ACC[k], 0.55) if k == cat else "transparent")
    def show_panel(self):
        if not self.feed.winfo_ismapped(): self.feed.pack(side="left", fill="y", padx=(2, 2), before=self.insp_box)
    def hide_panel(self): self.feed.pack_forget()
    def _inside(self):
        try: w = self.winfo_containing(*self.winfo_pointerxy())
        except Exception: return False
        while w is not None:
            if w is self.feed or w in self.navbtn.values(): return True
            w = getattr(w, "master", None)
        return False
    def hover_open(self, cat):
        if self.pinned or self.sel is not None: return
        if self._hj: self.after_cancel(self._hj); self._hj = None
        self.cat = cat; self.items = list(database.load_local_catalog(cat)); self.mark_nav(cat); self.show_genres(); self.show_panel()
    def hover_leave(self, e=None):
        if self.pinned: return
        if self._hj: self.after_cancel(self._hj)
        self._hj = self.after(350, self._maybe_close)
    def _maybe_close(self):
        self._hj = None
        if not self.pinned and not self._inside(): self.hide_panel(); self.mark_nav(None)
    def click_cat(self, cat):
        shown = self.feed.winfo_ismapped()
        if self.pinned and self.cat == cat and shown: self.pinned = False; self.hide_panel(); return
        if self.cat == cat and not shown and self.sel is not None and self.sel_cat == cat: self.pinned = True; self.show_panel(); return
        self.pinned = True; self.open_cat(cat)
    def pick_genre(self, n):
        if not self.pinned: self.pinned = True; self.open_cat(self.cat)
        self.show_feed(n)
    def home(self):
        self.open_cat("music"); self.hide_panel(); self.mark_nav(None)
        self.hero.play(os.path.join(MEDIA, "ambient", "music.mp4"), "music", ACC["music"], None, ("DISCOVER", "Hover a category to explore what's happening near you"), dim=0.65)
    def poll_ui(self):
        try:
            while True: fn, a = self.uiq.get_nowait(); fn(*a)
        except queue.Empty: pass
        self.after(200, self.poll_ui)
    def open_cat(self, cat):
        self.cat, self.sel = cat, None; acc = ACC[cat]
        self.items = list(database.load_local_catalog(cat)); self.mark_nav(cat)
        name = next(n for k, _, n in NAV if k == cat)
        amb = os.path.join(MEDIA, "ambient", cat + ".mp4")
        self.hero.play(amb, FXK[cat], acc, None, (name.upper(), TAG[cat]), dim=0.65)
        self.theater.play(None, FXK[cat], acc, None, ("Select a title", "Pick a genre, then choose from the trending feed"))
        self.title.configure(text="Pick a genre, then a title"); self.meta_lbl.configure(text=""); self.desc.configure(text="")
        self.close_bio(); self.poster.pack_forget(); [b.pack_forget() for b in (self.find_btn, self.buy_btn, self.trailer_btn, self.mute_btn)]; self.show_promo(True)
        for f in (self.cast_row, self.ev_box):
            for w in f.winfo_children(): w.destroy()
        self.show_genres(); self.show_panel()
    def show_genres(self):
        self.genre = None; self.back.pack_forget(); self.feed_title.configure(text="Events" if self.cat in UNIT else "Genres")
        for w in self.list.winfo_children(): w.destroy()
        cnt = {}
        for it in self.items: cnt[self.genre_of(it)] = cnt.get(self.genre_of(it), 0) + 1
        tiles = [("All", "⭐", len(self.items))] + [(n, ic, cnt.get(n, 0)) for n, ic in GENRES[self.cat]]
        self.list.grid_columnconfigure((0, 1), weight=1)
        for i, (n, ic, c) in enumerate(tiles):
            ctk.CTkButton(self.list, text=f"{ic}  {n}\n{c} {UNIT.get(self.cat, 'title')}{'s' if c != 1 else ''}", height=92, corner_radius=16, font=("Segoe UI", 17, "bold"),
                          fg_color=hexc(ACC[self.cat], 0.32 + 0.05 * (i % 5)), hover_color=hexc(ACC[self.cat], 0.75), command=lambda n=n: self.pick_genre(n)).grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")
    def show_feed(self, genre):
        self.genre = genre; self.back.pack(side="left", before=self.feed_title); self.feed_title.configure(text=f"{genre} · {TAG[self.cat]}" if genre != "All" else TAG[self.cat])
        for w in self.list.winfo_children(): w.destroy()
        self.list.grid_columnconfigure((0, 1), weight=0)
        rows = [i for i in self.items if genre == "All" or self.genre_of(i) == genre]
        rows.sort(key=lambda i: -float(g(i, "score", 0) or 0)); self.shown, self.cards, self.imgs = rows, {}, []
        if not rows: ctk.CTkLabel(self.list, text="Nothing here yet.\nAdd titles or run the scraper.", text_color="#888", font=("Segoe UI", 15)).pack(pady=40)
        for n, it in enumerate(rows):
            row = ctk.CTkFrame(self.list, fg_color=CARD, corner_radius=14, height=108); row.pack(fill="x", padx=4, pady=5); row.pack_propagate(False)
            im = ctk.CTkImage(art(g(it, "title"), ACC[self.cat], (116, 172)), size=(58, 86)); self.imgs.append(im)
            ctk.CTkLabel(row, text="", image=im).pack(side="left", padx=10, pady=8)
            col = ctk.CTkFrame(row, fg_color="transparent"); col.pack(side="left", fill="both", expand=True, pady=10)
            ctk.CTkLabel(col, text=f"#{n + 1}", font=("Segoe UI", 12, "bold"), text_color=hexc(ACC[self.cat]), anchor="w").pack(fill="x")
            ctk.CTkLabel(col, text=g(it, "title"), font=("Segoe UI", 17, "bold"), anchor="w", justify="left", wraplength=190).pack(fill="x")
            ctk.CTkLabel(col, text=f"{sub_of(it)} · {g(it, 'year')}".strip(" ·"), font=("Segoe UI", 13), text_color="#9aa0b5", anchor="w").pack(fill="x")
            ctk.CTkLabel(row, text=f"{float(g(it, 'score', 0) or 0):.0f}", width=46, height=46, corner_radius=23, fg_color=hexc(ACC[self.cat], 0.6), font=("Segoe UI", 16, "bold")).pack(side="right", padx=10)
            bind_all(row, lambda e, n=n: self.select(n)); self.cards[n] = row

    # ---------- detail page ----------
    def find_video(self, title):
        for ext in ("mp4", "mov", "mkv", "webm"):
            for folder in (VIDEOS, LEGACY_VIDEOS):
                path = os.path.join(folder, slug(title) + "." + ext)
                if os.path.exists(path): return path
        return None
    def avatar(self, name, size=96):
        pp = os.path.join(PEOPLE, slug(name) + ".jpg"); acc = tuple(70 + (zlib.crc32(name.encode()) >> s) % 150 for s in (0, 8, 16)); S = size * 4
        src = ImageOps.fit(Image.open(pp).convert("RGB"), (S, S), centering=(0.5, 0.2)) if os.path.exists(pp) else art(name, acc, (S, S), True)
        mk = Image.new("L", (S, S), 0); ImageDraw.Draw(mk).ellipse((0, 0, S - 1, S - 1), fill=255); mk = mk.resize((size, size), Image.LANCZOS)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0)); out.paste(src.resize((size, size), Image.LANCZOS).convert("RGBA"), (0, 0), mk)
        return ctk.CTkImage(out, size=(size, size))
    def select(self, n):
        it = self.shown[n]; self.sel = it; self.sel_cat = self.cat; self.close_bio(); self.show_promo(False)
        for k, c in self.cards.items(): c.configure(fg_color=hexc(ACC[self.cat], 0.35) if k == n else CARD)
        self.render_detail(it); self.fetch_online(it)
        if self.auto_var.get() and self.meta.get(self.cat, g(it, "title")).get("yt_id"): self.play_trailer()
    def render_detail(self, it):
        cat = self.sel_cat; acc = ACC[cat]; title = g(it, "title"); m = self.meta.get(cat, title); city = (self.gate.user or {}).get("city", "") if hasattr(self, "gate") else ""
        vid = m.get("video") if m.get("video") and os.path.exists(m["video"]) else self.find_video(title)
        bp = os.path.join(BACKDROPS, slug(title) + ".jpg"); still = Image.open(bp).convert("RGB") if os.path.exists(bp) and not vid else None
        self.theater.on_click = self.play_trailer if m.get("yt_id") else None; self.theater.configure(cursor="hand2" if m.get("yt_id") else "")
        self.theater.play(vid, "wave" if cat == "music" else FXK[cat], acc, None, (title, ("TRAILER · muted loop" if vid else ("▶ click to play the trailer" if m.get("yt_id") else ("WAVEFORM" if cat == "music" else "Trailer loading…"))) + f"  ·  {sub_of(it)}"), still=still)
        ps = (300, 300) if cat == "music" else (250, 375); self.poster.configure(image=ctk.CTkImage(art(title, acc, (ps[0] * 2, ps[1] * 2)), size=ps)); self.poster.pack(side="left", anchor="n", padx=(0, 12), before=self.theater)
        for b in (self.find_btn, self.trailer_btn, self.mute_btn, self.buy_btn): b.pack_forget()
        if m.get("yt_id"): self.trailer_btn.pack(side="left", padx=8)
        else: self.find_btn.pack(side="left", padx=8)
        if self.theater.vlc_on: self.mute_btn.configure(text="🔇  Sound off" if self.theater.muted else "🔊  Sound on"); self.mute_btn.pack(side="left", padx=8)
        if m.get("buy_url"): self.buy_btn.configure(text="🛒  " + m.get("buy_label", "Buy / Rent")); self.buy_btn.pack(side="left", padx=8)
        extra = "   •   ".join(x for x in (m.get("rated"), m.get("runtime")) if x)
        lead = ("🤝 Community listing   •   " if m.get("community") else "") + f"📅 {g(it, 'recent_shown')}" if cat in UNIT else f"★ {g(it, 'score')}   •   First: {g(it, 'first_shown')}   •   Latest: {g(it, 'recent_shown')}"
        self.title.configure(text=f"{title} ({g(it, 'year')})" if g(it, "year") else title)
        self.meta_lbl.configure(text=f"{sub_of(it)}   •   {self.genre_of(it)}   •   {lead}" + (f"   •   {extra}" if extra else ""))
        self.desc.configure(text=g(it, "description")); self.render_cast(it)
        for w in self.about_box.winfo_children(): w.destroy()
        about = m.get("about")
        ctk.CTkLabel(self.about_box, text=about or "Extended details load from the web the first time you open a title (needs internet).", font=("Segoe UI", 15), text_color="#cfd3e0" if about else "#888",
                     justify="left", anchor="w", wraplength=max(400, self.insp.winfo_width() - 120)).pack(fill="x")
        if m.get("about_url"): ctk.CTkButton(self.about_box, text="Read more on Wikipedia", fg_color=CARD, hover_color=HOVER, command=lambda u=m["about_url"]: webbrowser.open(u)).pack(anchor="w", pady=6)
        if m.get("tmdb_url"):
            ctk.CTkButton(self.about_box, text="Full cast, crew & details on TMDB", fg_color=CARD, hover_color=HOVER, command=lambda u=m["tmdb_url"]: webbrowser.open(u)).pack(anchor="w", pady=2)
            ctk.CTkLabel(self.about_box, text="This product uses the TMDB API but is not endorsed or certified by TMDB.", text_color="#777", font=("Segoe UI", 11)).pack(anchor="w")
        for w in self.ev_box.winfo_children(): w.destroy()
        evs = database.load_details(g(it, "id"))[1]
        if not evs:
            ctk.CTkLabel(self.ev_box, text="No saved dates yet. Search ticket vendors:", text_color="#888").pack(anchor="w"); self.vendor_row(self.ev_box, title, cat)
        for ev in evs:
            r = ctk.CTkFrame(self.ev_box, fg_color=CARD, corner_radius=12); r.pack(fill="x", pady=4)
            ctk.CTkLabel(r, text=f"📍  {g(ev, 'venue_name')}\n{g(ev, 'event_time')}  ·  {g(ev, 'location_details')}", font=("Segoe UI", 15), justify="left", anchor="w").pack(side="left", padx=14, pady=10)
            right = ctk.CTkFrame(r, fg_color="transparent"); right.pack(side="right", padx=10); real = g(ev, "purchase_url")
            if real: ctk.CTkButton(right, text="🎟  Reserve / Buy Tickets", fg_color="#1E7A34", hover_color="#27a046", command=lambda u=real: webbrowser.open(u)).pack(side="left", padx=3)
            for name, url in events.vendor_links(f"{title} {g(ev, 'venue_name')}" if cat != "sports" else title, cat)[: (2 if real else 3)]:
                ctk.CTkButton(right, text=name, width=90, fg_color="#2a2a3c" if real else "#1E7A34", hover_color=HOVER, command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=3)
        self.notes.delete("1.0", "end"); self.notes.insert("1.0", g(it, "user_notes"))
    def vendor_row(self, parent, query, cat):
        r = ctk.CTkFrame(parent, fg_color="transparent"); r.pack(anchor="w", pady=4)
        for name, url in events.vendor_links(query, cat): ctk.CTkButton(r, text=f"🎟  {name}", width=120, fg_color="#1E7A34", hover_color="#27a046", command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=4)
    def toggle_sound(self):
        self.mute_btn.configure(text="🔇  Sound off" if self.theater.toggle_mute() else "🔊  Sound on")
    def play_trailer(self):
        """YouTube's own player in its own window (needs pywebview); otherwise the video opens in your browser."""
        if not self.sel: return
        title = g(self.sel, "title"); vid = self.meta.get(self.sel_cat, title).get("yt_id")
        if not vid: return self.find_online()
        if importlib.util.find_spec("webview"):
            try:
                if getattr(self, "_tproc", None) and self._tproc.poll() is None: self._tproc.terminate()   # one trailer window at a time
                self._tproc = subprocess.Popen([sys.executable, os.path.join(BASE, "trailer_window.py"), vid, title]); return
            except Exception: pass
        webbrowser.open("https://www.youtube.com/watch?v=" + vid)
    def people_grid(self, parent, rows):
        grid = ctk.CTkFrame(parent, fg_color="transparent"); grid.pack(fill="x"); acc = ACC[self.sel_cat]; cols = max(1, (self.insp.winfo_width() - 70) // 186)
        for i, mem in enumerate(rows):
            nm = g(mem, "name"); c = ctk.CTkFrame(grid, width=170, fg_color=CARD, corner_radius=16, cursor="hand2"); c.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="n")
            ctk.CTkLabel(c, text="", image=self.avatar(nm)).pack(pady=(14, 4), padx=18)
            ctk.CTkLabel(c, text=nm, font=("Segoe UI", 16, "bold"), wraplength=150).pack(padx=8)
            ctk.CTkLabel(c, text=g(mem, "role_type"), font=("Segoe UI", 13, "bold"), text_color=hexc(acc), wraplength=150).pack(pady=(0, 4))
            ctk.CTkLabel(c, text="View bio ›", font=("Segoe UI", 12), text_color="#9aa0b5").pack(pady=(0, 12))
            bind_all(c, lambda e, mem=mem: self.open_bio(mem))
    def render_cast(self, it):
        for w in self.cast_row.winfo_children(): w.destroy()
        rows = database.load_details(g(it, "id"))[0]; cast = [r for r in rows if not is_crew(g(r, "role_type"))]; crew = [r for r in rows if is_crew(g(r, "role_type"))]
        iid = g(it, "id"); more = self.cast_all == iid
        if cast: self.people_grid(self.cast_row, cast if more else cast[:12])
        if len(cast) > 12:
            ctk.CTkButton(self.cast_row, text="Show fewer" if more else f"Show all {len(cast)} cast", fg_color=CARD, hover_color=HOVER,
                          command=lambda: (setattr(self, "cast_all", None if more else iid), self.render_cast(it))).pack(anchor="w", pady=6)
        if crew:
            ctk.CTkLabel(self.cast_row, text="Crew", font=("Segoe UI", 18, "bold"), anchor="w").pack(fill="x", pady=(14, 0)); self.people_grid(self.cast_row, crew)
    def fetch_online(self, it):
        """Background: poster, backdrop, trailer, buy link, About text and the FULL cast/crew (with photos). Results return through self.uiq."""
        cat, title, sub, year, iid = self.sel_cat, g(it, "title"), sub_of(it), str(g(it, "year")), g(it, "id"); mm = self.meta.get(cat, title); key = events.load_cfg().get("tmdb_key", "")
        need = (not mm.get("online_v3") and time.time() - mm.get("online_try", 0) > 86400 * 3) or bool(key and cat in ("movies", "tv") and not mm.get("tmdb_id") and time.time() - mm.get("tmdb_try", 0) > 3600)
        rows = database.load_details(iid)[0][:8]
        fresh = [g(x, "name") for x in rows if not os.path.exists(os.path.join(PEOPLE, slug(g(x, "name")) + ".jpg")) and online.cached_person(PEOPLE, g(x, "name")) is None]
        if not need and not fresh: return
        def work():
            res, ppl = None, False
            try:
                if need: res = online.fetch(cat, title, sub, year, POSTERS, VIDEOS, slug(title), key, BACKDROPS, PEOPLE)
            except Exception: pass
            for nm in ([] if res and res.get("credits") else fresh):
                try: online.person(PEOPLE, nm); ppl = True
                except Exception: break
            self.uiq.put((self.apply_online, (cat, title, res, ppl, iid)))
        threading.Thread(target=work, daemon=True).start()
    def apply_online(self, cat, title, res, ppl, iid):
        if res is not None:
            credits = res.pop("credits", None)
            if credits: database.add_credits(iid, credits)
            self.meta.put(cat, title, **({"online_v3": True, **res} if res else {"online_try": time.time()}))
            if events.load_cfg().get("tmdb_key") and cat in ("movies", "tv") and not res.get("tmdb_id"): self.meta.put(cat, title, tmdb_try=time.time())
        for k in [k for k in _ART if k[0] == title]: del _ART[k]
        if self.sel is not None and self.sel_cat == cat and g(self.sel, "title") == title:
            if res: self.render_detail(self.sel)
            elif ppl: self.render_cast(self.sel)
            if res and res.get("yt_id") and self.auto_var.get(): self.play_trailer()
    def poster_dir(self): return POSTERS
    def open_promote(self):
        self.gate.place_forget(); self.close_bio(); self.close_promote(); self._promo = promote.PromoteForm(self, self.insp_box)
    def close_promote(self):
        if getattr(self, "_promo", None) is not None:
            try: self._promo.destroy()
            except Exception: pass
            self._promo = None
    def sync_community(self, say=None):
        """Background: download the curated community feed (if one is configured) and merge it into the library."""
        if not community.feed_url():
            if say: say("Community feed isn't set up yet (set community_feed_url).")
            return
        def work():
            try: res = community.sync(self.poster_dir())
            except Exception as e: return self.uiq.put((say or (lambda s: None), (f"Community feed unavailable: {e}",)))
            self.uiq.put((self.apply_community, (res, say)))
        threading.Thread(target=work, daemon=True).start()
    def apply_community(self, res, say=None):
        if not res: return
        for (cat, title), kw in res["meta"].items(): self.meta.d.setdefault(f"{cat}|{title}", {}).update(kw)
        self.meta.save()
        if "count" in res:
            msg = f"Community events: {res['count']} listed." + (f" {res['pruned']} removed." if res.get("pruned") else "")
            if say: say(msg)
            if self.gate.winfo_ismapped(): self.gate.show_dashboard(msg)
    def sync_events(self, say, scope="nearby"):
        """Load Ticketmaster listings near the user's ZIP or across their state."""
        u = self.gate.user or {}; key = events.load_cfg().get("ticketmaster_key", "")
        if not key: return say("Paste your free Ticketmaster key first (use the Get a free key link).")
        statewide = scope == "state"
        if statewide and not u.get("state"): return say("Add a ZIP code to your account so we know which state to search.")
        if not statewide and not u.get("lat"): return say("Sign in with an account that has a ZIP code so we know what is near you.")
        search_label = f"all of {u['state']}" if statewide else "near you"
        say("Starting…")
        def work():
            try: res = events.sync(key, u.get("lat"), u.get("lng"), POSTERS, lambda s: self.uiq.put((say, (s,))), state_code=u.get("state") if statewide else None)
            except Exception as e: return self.uiq.put((say, (f"Sync failed: {e}",)))
            self.uiq.put((self.apply_sync, (res, search_label)))
        threading.Thread(target=work, daemon=True).start()
    def apply_sync(self, res, search_label="near you"):
        for (cat, title), kw in res["meta"].items(): self.meta.d.setdefault(f"{cat}|{title}", {}).update(kw)
        self.meta.save(); self.gate.show_dashboard(f"Done: {res['sports']} sports, {res['festivals']} festival events, {res['tours']} tour dates found {search_label}.")
    def open_buy(self):
        if self.sel: url = self.meta.get(self.sel_cat, g(self.sel, "title")).get("buy_url"); url and webbrowser.open(url)
    def close_bio(self):
        if self._bio is not None:
            try: self._bio.destroy()
            except Exception: pass
            self._bio = None
    def open_bio(self, mem):
        self.close_bio(); nm = g(mem, "name"); acc = ACC[self.sel_cat]
        ov = ctk.CTkFrame(self.insp_box.master, fg_color=BG, corner_radius=0); ov.place(in_=self.insp_box, x=0, y=0, relwidth=1, relheight=1); self._bio = ov
        ctk.CTkButton(ov, text="‹  Back", width=90, fg_color=CARD, hover_color=HOVER, command=self.close_bio).pack(anchor="w", padx=24, pady=(18, 8))
        row = ctk.CTkFrame(ov, fg_color="transparent"); row.pack(fill="both", expand=True, padx=24, pady=8)
        photo = ctk.CTkLabel(row, text=""); photo.pack(side="left", anchor="n", padx=(0, 24))
        col = ctk.CTkFrame(row, fg_color="transparent"); col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(col, text=nm, font=("Segoe UI", 34, "bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(col, text=g(mem, "role_type"), font=("Segoe UI", 18, "bold"), text_color=hexc(acc), anchor="w").pack(fill="x")
        known = ", ".join(t for _, t in database.titles_for_person(nm))
        if known: ctk.CTkLabel(col, text="In your library: " + known, text_color="#9aa0b5", anchor="w", justify="left", wraplength=700).pack(fill="x", pady=(2, 10))
        box = ctk.CTkTextbox(col, fg_color=CARD, font=("Segoe UI", 15), wrap="word"); box.pack(fill="both", expand=True)
        link = ctk.CTkButton(col, text="Full biography on Wikipedia", fg_color=CARD, hover_color=HOVER)
        def fill(p):
            if self._bio is not ov or not ov.winfo_exists(): return
            ok = bool(p and not p.get("missing")); txt = p["bio"] if ok else (g(mem, "biography") or "No biography found yet.")
            box.configure(state="normal"); box.delete("1.0", "end"); box.insert("1.0", txt); box.configure(state="disabled")
            pp = os.path.join(PEOPLE, slug(nm) + ".jpg")
            if os.path.exists(pp): img = ImageOps.fit(Image.open(pp).convert("RGB"), (520, 680), centering=(0.5, 0.2))
            else: img = art(nm, tuple(70 + (zlib.crc32(nm.encode()) >> s) % 150 for s in (0, 8, 16)), (520, 680), True)
            photo.configure(image=ctk.CTkImage(img, size=(260, 340)))
            if ok and p.get("url"): link.configure(command=lambda: webbrowser.open(p["url"])); link.pack(anchor="e", pady=6)
        c = online.cached_person(PEOPLE, nm); fill(c)
        if c is None:
            def work():
                try: p = online.person(PEOPLE, nm)
                except Exception: return
                self.uiq.put((fill, (p,)))
            threading.Thread(target=work, daemon=True).start()
    def attach_video(self):
        if not self.sel: return messagebox.showinfo("Spotlight", "Select a title first.")
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.mkv *.webm *.avi")])
        if f:
            t = g(self.sel, "title"); dst = os.path.join(VIDEOS, slug(t) + os.path.splitext(f)[1].lower()); shutil.copy(f, dst)
            self.meta.put(self.sel_cat, t, video=dst); self.render_detail(self.sel)
    def find_online(self):
        if self.sel: webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(f"{g(self.sel, 'title')} {sub_of(self.sel)} " + ("live performance" if self.sel_cat == "music" else "official trailer")))
    def save_notes(self):
        if self.sel:
            txt = self.notes.get("1.0", "end").strip(); database.update_notes(g(self.sel, "id"), txt)
            try: self.sel["user_notes"] = txt
            except Exception: pass
            messagebox.showinfo("Spotlight", "Notes saved.")

    # ---------- network status ----------
    def start_sentinel(self):
        def loop():
            while True:
                try: urllib.request.urlopen("https://www.google.com", timeout=3); self.online = True
                except Exception: self.online = False
                time.sleep(8)
        threading.Thread(target=loop, daemon=True).start()
    def poll_status(self):
        self.hero.status = ("● Checking connection", "#FFB300") if self.online is None else (("● Online · synced", "#4CAF50") if self.online else ("● Offline · local library active", "#FF9800"))
        self.after(1000, self.poll_status)

if __name__ == "__main__":
    App().mainloop()
