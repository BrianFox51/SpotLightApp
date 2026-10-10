"""Spotlight - Local Media Dashboard. Install required packages from requirements.txt."""
import os, re, sys, json, math, time, queue, zlib, shutil, threading, subprocess, importlib.util, webbrowser, urllib.request, urllib.parse
import tkinter as tk
from tkinter import messagebox, filedialog, font as tkfont
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
NAV = [("music", "🎵", "Concerts & Music"), ("movies", "🎬", "Cinema Feeds"), ("tv", "📺", "TV Networks"), ("games", "🎮", "Gaming Hub"), ("sports", "🏆", "Sports & Events"), ("festivals", "🎪", "Festivals & Fairs")]
ACC = {"music": (214, 64, 190), "movies": (226, 72, 58), "tv": (36, 182, 196), "games": (84, 214, 108), "sports": (255, 140, 40), "festivals": (150, 110, 255)}
FXK = {"music": "music", "movies": "movies", "tv": "tv", "games": "games", "sports": "tv", "festivals": "music"}
TAG = {"music": "Upcoming concerts & music events", "movies": "Now showing", "tv": "TV airing this week", "games": "Playing now", "sports": "Upcoming events", "festivals": "Happening soon"}
UNIT = {"music": "event", "sports": "event", "festivals": "event"}
GENRES = {"music": [("Pop", "🎤"), ("Hip-Hop", "🎧"), ("Rock", "🎸"), ("Electronic", "🎛️"), ("R&B", "💜"), ("Country", "🤠"), ("Latin", "💃"), ("Jazz", "🎷"), ("Other", "🎼")],
          "movies": [("Action", "💥"), ("Drama", "🎭"), ("Comedy", "😂"), ("Sci-Fi", "🚀"), ("Horror", "👻"), ("Thriller", "🔪"), ("Animation", "✏️"), ("Indie", "🎞️")],
          "tv": [("Drama", "🎭"), ("Comedy", "😂"), ("Sci-Fi", "🚀"), ("Reality", "📡"), ("Docs", "🌍"), ("Animation", "✏️")],
          "games": [("Action", "⚔️"), ("RPG", "🐉"), ("Strategy", "♟️"), ("Shooter", "🎯"), ("Indie", "🕹️"), ("Sports", "🏆")],
          "sports": [("Baseball", "⚾"), ("Basketball", "🏀"), ("Football", "🏈"), ("Hockey", "🏒"), ("Soccer", "⚽"), ("Golf", "⛳"), ("Tennis", "🎾"), ("Racing", "🏁"), ("MMA & Boxing", "🥊"),
                     ("Wrestling", "🤼"), ("Rodeo", "🤠"), ("Poker", "🃏"), ("Bowling", "🎳"), ("Pool & Billiards", "🎱"), ("Darts", "🎯"), ("Esports", "🎮")],
          "festivals": [("Harvest & Food", "🎃"), ("County & State Fairs", "🎡"), ("Music Festivals", "🎶"), ("Arts & Crafts", "🎨"), ("Parades & Holidays", "🎆"), ("Cultural", "🌍"), ("Film Festivals", "🎬"), ("Car Shows", "🚗"), ("Renaissance & Fantasy", "🏰")]}
# (cat, title, sub, year, score, desc, first_shown, recent_shown, genre, [(name, role, bio)], [(venue, time, location)])  -- demo data
SEED = [
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

def wrapped_height(root, text, size, width, bold=False):
    """Estimate the height needed to show every wrapped line in a CTk label."""
    scale = root._get_widget_scaling()
    font = tkfont.Font(root=root, family="Segoe UI", size=-max(1, round(size * scale)), weight="bold" if bold else "normal")
    measured_width = width * scale
    line_width = 0
    lines = 0
    for paragraph in str(text or "").splitlines() or [""]:
        if not paragraph.strip():
            lines += 1
            continue
        for word in paragraph.split():
            word_width = font.measure(word)
            space_width = font.measure(" ") if line_width else 0
            if line_width and line_width + space_width + word_width > measured_width:
                lines += 1
                line_width = word_width
            else:
                line_width += space_width + word_width
        lines += 1
        line_width = 0
    return max(24, math.ceil(lines * (font.metrics("linespace") + 2 * scale) / scale) + 4)

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
    tmdb_cinema_logo = None
    """Looping video (muted) or generated animation. One decoder thread at a time; switching items cancels the old one."""
    def __init__(self, master, mode, height):
        super().__init__(master, height=height, highlightthickness=0, bg="#08080c")
        self.mode, self.gen, self.video, self.failed, self.q = mode, 0, None, False, queue.Queue(maxsize=2)
        self.kind, self.accent, self.cover, self.lines, self.dim = "movies", ACC["movies"], None, ("", ""), 1.0
        self.t0, self.photo, self.size, self.status = time.time(), None, (0, 0), ("", "#888888")
        self.vinst = self.vp = self.vf = None; self.vlc_on = False; self.audio_only = False; self.muted = True; self.still = self.on_click = self._sk = None
        self.bind("<Button-1>", lambda e: self.on_click and self.on_click())
        self.after(50, self.tick)
    def play(self, video, kind, accent, cover=None, lines=("", ""), dim=1.0, still=None):
        self.muted = True
        self.still, self._sk = still, None; self.gen += 1; self.failed = False; self.audio_only = False; self.video = video if video and os.path.exists(video) else None
        self.kind, self.accent, self.cover, self.lines, self.dim = kind, accent, cover, lines, dim
        while not self.q.empty():
            try: self.q.get_nowait()
            except queue.Empty: break
        if self.mode == "theater":
            if self.video and self.vlc_start(self.video): return
            self.vlc_stop()
        if self.video: threading.Thread(target=self.decode, args=(self.gen, self.video), daemon=True).start()
    def play_audio(self, path, kind, accent, lines=("", ""), dim=1.0, still=None):
        """Play a muted audio preview while keeping the generated waveform visible."""
        self.play(None, kind, accent, None, lines, dim, still)
        if self.mode == "theater" and path and os.path.exists(path):
            self.vlc_start(path, audio_only=True)
    def vlc_start(self, path, audio_only=False):
        """Optional: play with sound through VLC (needs python-vlc + VLC installed). Returns False so the silent built-in player is used instead."""
        try:
            import vlc
            if self.vinst is None: self.vinst = vlc.Instance("--quiet", "--no-video-title-show")
            self.audio_only = audio_only
            if audio_only:
                if self.vf is not None: self.vf.place_forget()
            else:
                if self.vf is None: self.vf = tk.Frame(self, bg="black")
                self.vf.place(x=0, y=0, relwidth=1, relheight=1); self.vf.update_idletasks()
            if self.vp is None: self.vp = self.vinst.media_player_new()
            self.vp.stop()
            if not audio_only:
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
        if self.vlc_on and not self.audio_only: self.after(250, self.tick); return
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
            (self.create_image(22, 8, image=Stage.logo, anchor="nw") if Stage.logo else txt(24, 12, "SPOTLIGHT", 15)); txt(w - 20, 16, self.status[0], 22, self.status[1], "ne", True)
            if self.lines[0].upper() in {"CINEMA FEEDS", "TV NETWORKS"}:
                if Stage.tmdb_cinema_logo:
                    self.create_image(22, 48, image=Stage.tmdb_cinema_logo, anchor="nw")
                txt(24, h - 72, self.lines[0], 26); txt(26, h - 8, self.lines[1], 18, "#f3f4f8", "sw", False)
            else:
                txt(24, h - 78, self.lines[0], 30); txt(26, h - 8, self.lines[1], 18, "#f3f4f8", "sw", False)
        else:
            n = len(self.lines[0]); txt(24, h - 74, self.lines[0], 24 if n <= 22 else 18 if n <= 34 else 14); txt(26, h - 16, self.lines[1], 18, "#f3f4f8", "sw", False)

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
        self.page = 0; self.search_job = None; self.search_active = False; self.search_results = []; self.search_query = ""
        self.uiq, self.sel_cat, self.pinned, self._hj, self._bio = queue.Queue(), None, False, None, None
        self.cast_all = self._tproc = None
        self.load_logos(); self.after(300, self.set_icon)
        self.seed(); self.build(); self.start_sentinel(); self.poll_status(); self.poll_ui(); self.bind("<Configure>", self.on_resize); self.home(); self.gate = dashboard.Gate(self, BASE); self.after(3000, self.sync_community)

    # ---------- data ----------
    def seed(self):
        if self.meta.d.get("_seeded_v4"): return
        # Remove only the four known sample tracks from earlier versions.
        sample_tracks = {"Blinding Lights", "As It Was", "SICKO MODE", "Bohemian Rhapsody"}
        for item in database.load_local_catalog("music"):
            if g(item, "title") in sample_tracks:
                try:
                    sources = json.loads(g(item, "sources", "[]") or "[]")
                except (TypeError, ValueError):
                    sources = []
                if "Demo" in sources:
                    database.delete_item(g(item, "id"))
        have = {c: {g(i, "title") for i in database.load_local_catalog(c)} for c in ACC}
        for cat, title, sub, year, score, desc, first, recent, genre, cast, ev in SEED:
            try:
                if title not in have[cat]:
                    database.save_media_item(cat, {"title": title, "sub": sub, "year": year, "url": "", "score": score, "desc": desc, "first_shown": first, "recent_shown": recent, "srcs": ["Demo"]},
                                             [{"name": n, "role": r, "bio": b} for n, r, b in cast], [{"venue": v, "time": t, "location": l, "purchase_url": ""} for v, t, l in ev])
            except Exception as e: print("seed skipped:", title, e)
            self.meta.d.setdefault(f"{cat}|{title}", {}).setdefault("genre", genre)
        self.meta.d["_seeded_v4"] = True; self.meta.save()

    def genre_of(self, it):
        metadata = self.meta.get(self.cat, g(it, "title"))
        genre = metadata.get("music_genre") if self.cat == "music" else None
        genre = genre or metadata.get("genre", "Other")
        # Older live listings stored their event type in this field.
        return "Other" if self.cat == "music" and genre in {"Bands & Live Shows", "Music Festivals"} else genre

    def music_type_of(self, it):
        metadata = self.meta.get("music", g(it, "title"))
        return metadata.get("music_type") or (metadata.get("genre") if metadata.get("genre") in {"Bands & Live Shows", "Music Festivals"} else "Bands & Live Shows")

    # ---------- layout ----------
    def build(self):
        self.hero = Stage(self, "hero", 150); self.hero.pack(fill="x")
        searchbar = ctk.CTkFrame(self, fg_color="#151520", corner_radius=0, height=58)
        searchbar.pack(fill="x"); searchbar.pack_propagate(False)
        ctk.CTkLabel(searchbar, text="⌕  SPOTLIGHT SEARCH  ·  Ctrl+K", text_color="#c9a45c", font=("Segoe UI", 13, "bold")).pack(side="left", padx=(18, 12))
        self.search_entry = ctk.CTkEntry(searchbar, height=38, placeholder_text="Find a concert, artist, movie, venue, game, or event…",
                                         font=("Segoe UI", 15), border_width=1, corner_radius=12)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=4, pady=8)
        self.search_entry.bind("<KeyRelease>", self.schedule_search)
        self.search_entry.bind("<Return>", lambda _event: self.run_search())
        self.search_scope = ctk.StringVar(value="Everywhere")
        self.search_scope_menu = ctk.CTkOptionMenu(searchbar, values=["Everywhere", "This section"], variable=self.search_scope,
                                                   width=145, height=38, command=lambda _choice: self.schedule_search())
        self.search_scope_menu.pack(side="left", padx=7)
        ctk.CTkButton(searchbar, text="×", width=38, height=38, fg_color=CARD, hover_color=HOVER,
                      command=self.clear_search).pack(side="left", padx=(0, 12))
        self.bind_all("<Control-k>", self.focus_search, add="+")
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0); body.pack(fill="both", expand=True)
        rail = ctk.CTkFrame(body, width=156, fg_color=PANEL, corner_radius=0); rail.pack(side="left", fill="y"); rail.pack_propagate(False)
        self.navbtn = {}
        hb = ctk.CTkButton(rail, text="🏠", width=60, height=52, corner_radius=14, font=("Segoe UI Emoji", 25), fg_color="transparent", hover_color=HOVER, command=lambda: self.gate.show_dashboard())
        hb.pack(pady=(10, 2), padx=12); Tip(hb, "Dashboard")
        for key, ico, name in NAV:
            b = ctk.CTkButton(rail, text=ico, width=60, height=52, corner_radius=14, font=("Segoe UI Emoji", 25), fg_color="transparent", hover_color=HOVER, command=lambda k=key: self.click_cat(k))
            b.pack(pady=(10, 2), padx=12); self.navbtn[key] = b; b.bind("<Enter>", lambda e, k=key: self.hover_open(k), add="+"); b.bind("<Leave>", self.hover_leave, add="+")
        pb = ctk.CTkButton(rail, text="📣  Promote\nyour event", width=140, height=64, corner_radius=14,
                           font=("Segoe UI", 14, "bold"), fg_color="#9b6a1c", hover_color="#c48a2a",
                           command=self.open_promote)
        pb.pack(side="bottom", fill="x", pady=12, padx=8)
        self.feed = ctk.CTkFrame(body, width=410, fg_color=PANEL, corner_radius=0); self.feed.pack(side="left", fill="y", padx=(2, 2)); self.feed.pack_propagate(False)
        top = ctk.CTkFrame(self.feed, fg_color="transparent"); top.pack(fill="x", padx=12, pady=(14, 6))
        self.back = ctk.CTkButton(top, text="‹", width=38, height=38, font=("Segoe UI", 24, "bold"), fg_color=CARD, hover_color=HOVER, command=self.back_to_list)
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
        self.mute_btn = ctk.CTkButton(bar, text="🔊  Unmute", fg_color=CARD, hover_color=HOVER, command=self.toggle_sound)
        self.title = ctk.CTkLabel(p, text="Pick a genre, then a title", font=("Segoe UI", 34, "bold"), anchor="w"); self.title.pack(fill="x", padx=20, pady=(14, 0))
        self.meta_lbl = ctk.CTkLabel(p, text="", font=("Segoe UI", 14), text_color="#9aa0b5", anchor="w"); self.meta_lbl.pack(fill="x", padx=20)
        self.desc = ctk.CTkLabel(p, text="", font=("Segoe UI", 16), text_color="#c8ccd8", justify="left", anchor="w", wraplength=800); self.desc.pack(fill="x", padx=20, pady=10)
        self.about_label = None; self.event_detail_labels = []
        self.promo = self.make_promo(p); self.promo.pack(fill="x", padx=20, pady=10); self.detail = ctk.CTkFrame(p, fg_color="transparent")
        self.cast_row = self.section("👥  Cast & Crew"); self.ev_box = self.section("📍  Local Venues & Showtimes")
        self.about_box = self.section("📖  About"); nb = self.section("📝  Notes")
        self.tmdb_notes_mark = ctk.CTkLabel(nb, text="")
        if self.tmdb_detail_image is not None:
            self.tmdb_notes_mark.configure(image=self.tmdb_detail_image)
        self.notes = ctk.CTkTextbox(nb, height=110, fg_color=CARD); self.notes.pack(fill="x", pady=4)
        ctk.CTkButton(nb, text="Save notes", command=self.save_notes).pack(anchor="e", pady=4)
    def section(self, label):
        ctk.CTkLabel(self.detail, text=label, font=("Segoe UI", 20, "bold"), anchor="w").pack(fill="x", padx=20, pady=(22, 6))
        f = ctk.CTkFrame(self.detail, fg_color="transparent"); f.pack(fill="x", padx=20); return f
    def on_resize(self, e=None):
        if self._rs: self.after_cancel(self._rs)
        def go():
            iw = self.insp.winfo_width()
            if iw > 200:
                text_width = max(180, self.insp._reverse_widget_scaling(iw) - 40)
                self.theater.configure(height=140 if self.sel is None else int(min(max(iw * 0.42, 300), 500)))
                logical_width = self.insp._reverse_widget_scaling(iw)
                title_size = max(20, min(34, logical_width // 22))
                title_text = self.title.cget("text")
                meta_text = self.meta_lbl.cget("text")
                desc_text = self.desc.cget("text")
                self.title.configure(font=("Segoe UI", title_size, "bold"), wraplength=text_width, justify="left",
                                     height=wrapped_height(self.insp, title_text, title_size, text_width, True))
                self.meta_lbl.configure(wraplength=text_width, justify="left", height=wrapped_height(self.insp, meta_text, 14, text_width))
                self.desc.configure(wraplength=text_width, height=wrapped_height(self.insp, desc_text, 16, text_width))
                if self.about_label is not None and self.about_label.winfo_exists():
                    about_text = self.about_label.cget("text")
                    self.about_label.configure(wraplength=text_width, height=wrapped_height(self.insp, about_text, 15, text_width))
                for label in self.event_detail_labels:
                    if label.winfo_exists():
                        event_width = max(180, self.insp._reverse_widget_scaling(iw) - 390)
                        label.configure(wraplength=event_width, height=wrapped_height(self.insp, label.cget("text"), 15, event_width))
        self._rs = self.after(150, go)

    def load_logos(self):
        self.logo_pil = dashboard.load_logo(BASE); Stage.logo = None
        if self.logo_pil is not None:
            wm = self.logo_pil.crop(dashboard.WORDMARK); Stage.logo = ImageTk.PhotoImage(wm.resize((190, int(190 * wm.height / wm.width)), Image.LANCZOS))
        cinema_logo = dashboard.load_tmdb_logo(BASE, "tmdb_cinema.png")
        Stage.tmdb_cinema_logo = ImageTk.PhotoImage(cinema_logo.resize((84, max(1, round(84 * cinema_logo.height / cinema_logo.width))), Image.LANCZOS)) if cinema_logo is not None else None
        detail_logo = dashboard.load_tmdb_logo(BASE, "tmdb_detail.png")
        self.tmdb_detail_image = ctk.CTkImage(detail_logo, size=(112, max(1, round(112 * detail_logo.height / detail_logo.width)))) if detail_logo is not None else None
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
        self.tmdb_promo_pil = dashboard.load_tmdb_logo(BASE, "tmdb_cinema.png")
        self.tmdb_promo_size = (104, max(1, round(104 * self.tmdb_promo_pil.height / self.tmdb_promo_pil.width))) if self.tmdb_promo_pil is not None else None
        self.tmdb_promo_ctk = None; self.tmdb_promo_label = ctk.CTkLabel(f, text="")
        self._tmdb_promo_job = None; self._tmdb_promo_steps = 20
        path = dashboard.find_banner(BASE)
        if path:
            im = Image.open(path).convert("RGB"); ci = ctk.CTkImage(im, size=(260, int(260 * im.height / im.width))); self._promo_imgs.append(ci)
            self.promo_banner = ctk.CTkLabel(f, text="", image=ci); self.promo_banner.pack(pady=(10, 0))
        else:
            self.promo_banner = None
        ctk.CTkButton(f, text="mythicmaskworks.com   ·   free app", fg_color="transparent", hover_color=HOVER, text_color="#c9a45c", font=("Segoe UI", 14, "bold"), command=lambda: webbrowser.open(dashboard.SITE)).pack(pady=4)
        return f
    def _show_tmdb_promo(self, opacity=1.0):
        if self.tmdb_promo_pil is None: return
        image = self.tmdb_promo_pil.copy()
        if opacity < 1:
            alpha = image.getchannel("A").point(lambda value: round(value * opacity))
            image.putalpha(alpha)
        self.tmdb_promo_ctk = ctk.CTkImage(image, size=self.tmdb_promo_size)
        self.tmdb_promo_label.configure(image=self.tmdb_promo_ctk)
        if not self.tmdb_promo_label.winfo_manager():
            self.tmdb_promo_label.pack(pady=(2, 6), before=self.promo_banner) if self.promo_banner else self.tmdb_promo_label.pack(pady=(2, 6))
    def _update_tmdb_promo(self):
        should_show = (self.cat in {"movies", "tv"} and self.sel is None
                       and self.feed.winfo_manager() == "pack" and self.promo.winfo_manager() == "pack")
        if should_show:
            if self._tmdb_promo_job:
                self.after_cancel(self._tmdb_promo_job); self._tmdb_promo_job = None
            self._show_tmdb_promo(1.0)
            return
        if self._tmdb_promo_job or not self.tmdb_promo_label.winfo_ismapped(): return
        self._tmdb_promo_steps = 20
        def dissolve():
            self._tmdb_promo_steps -= 1
            self._show_tmdb_promo(max(0, self._tmdb_promo_steps / 20))
            if self._tmdb_promo_steps <= 0:
                self.tmdb_promo_label.pack_forget(); self._tmdb_promo_job = None
            else:
                self._tmdb_promo_job = self.after(100, dissolve)
        self._tmdb_promo_job = self.after(100, dissolve)
    def show_promo(self, on):
        if on: self.detail.pack_forget(); self.promo.pack(fill="x", padx=20, pady=10)
        else: self.promo.pack_forget(); self.detail.pack(fill="x")
        self._update_tmdb_promo()
        self.on_resize()

    # ---------- navigation ----------
    def mark_nav(self, cat):
        for k, b in self.navbtn.items(): b.configure(fg_color=hexc(ACC[k], 0.55) if k == cat else "transparent")
    def show_panel(self):
        if not self.feed.winfo_ismapped(): self.feed.pack(side="left", fill="y", padx=(2, 2), before=self.insp_box)
        self._update_tmdb_promo()
    def hide_panel(self):
        self.feed.pack_forget(); self._update_tmdb_promo()
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
        if self.search_active:
            self.clear_search()
        shown = self.feed.winfo_ismapped()
        if self.pinned and self.cat == cat and shown: self.pinned = False; self.hide_panel(); return
        if self.cat == cat and not shown and self.sel is not None and self.sel_cat == cat: self.pinned = True; self.show_panel(); return
        self.pinned = True; self.open_cat(cat)
    def pick_genre(self, n):
        if not self.pinned: self.pinned = True; self.open_cat(self.cat)
        self.page = 0
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
        self.hero.configure(height=190 if cat in {"movies", "tv"} else 150)
        self.items = list(database.load_local_catalog(cat)); self.mark_nav(cat)
        name = next(n for k, _, n in NAV if k == cat)
        amb = os.path.join(MEDIA, "ambient", cat + ".mp4")
        self.hero.play(amb, FXK[cat], acc, None, (name.upper(), TAG[cat]), dim=0.65)
        self.theater.play(None, FXK[cat], acc, None, ("Select an event" if cat == "music" else "Select a title", "Pick a genre or event type, then choose an event" if cat == "music" else "Pick a genre, then choose from the trending feed"))
        self.title.configure(text="Choose a genre or event type" if cat == "music" else "Pick a genre, then a title"); self.meta_lbl.configure(text=""); self.desc.configure(text="")
        self.close_bio(); self.poster.pack_forget(); [b.pack_forget() for b in (self.find_btn, self.buy_btn, self.trailer_btn, self.mute_btn)]; self.show_promo(True)
        for f in (self.cast_row, self.ev_box):
            for w in f.winfo_children(): w.destroy()
        self.show_genres(); self.show_panel()
    def show_genres(self):
        self.search_active = False; self.search_results = []
        self.genre = None; self.back.pack_forget(); self.feed_title.configure(text="Events" if self.cat in UNIT else "Genres")
        for w in self.list.winfo_children(): w.destroy()
        cnt = {}
        if self.cat == "music":
            for item in self.items:
                for label in (self.genre_of(item), self.music_type_of(item)):
                    cnt[label] = cnt.get(label, 0) + 1
            tiles = ([ ("All", "⭐", len(self.items)) ] if self.items else [])
            tiles.extend((name, icon, cnt.get(name, 0)) for name, icon in (("Bands & Live Shows", "🎤"), ("Music Festivals", "🎪")) if cnt.get(name, 0))
            tiles.extend((name, icon, cnt.get(name, 0)) for name, icon in GENRES[self.cat] if cnt.get(name, 0))
        else:
            for it in self.items: cnt[self.genre_of(it)] = cnt.get(self.genre_of(it), 0) + 1
            tiles = ([ ("All", "⭐", len(self.items)) ] if self.items else [])
            tiles.extend((n, ic, cnt.get(n, 0)) for n, ic in GENRES[self.cat] if cnt.get(n, 0))
            known_genres = {name for name, _icon in GENRES[self.cat]}
            icon = "🎬" if self.cat == "movies" else "📺"
            tiles.extend((name, icon, count) for name, count in sorted(cnt.items()) if name not in known_genres)
        if not tiles:
            empty = "No events have been found in this section yet." if self.cat in UNIT else "No items have been saved in this section yet."
            ctk.CTkLabel(self.list, text=empty + "\nTry Spotlight Search above or sync events from the dashboard.",
                         text_color="#9aa0b5", font=("Segoe UI", 15), wraplength=300, justify="left").pack(padx=18, pady=32)
        self.list.grid_columnconfigure((0, 1), weight=1)
        for i, (n, ic, c) in enumerate(tiles):
            display_name = n.replace(" & ", " &\n") if len(n) > 15 and " & " in n else n.replace(" ", "\n", 1) if len(n) > 15 else n
            ctk.CTkButton(self.list, text=f"{ic}  {display_name}\n{c} {UNIT.get(self.cat, 'title')}{'s' if c != 1 else ''}", height=92, corner_radius=16, font=("Segoe UI", 15, "bold"),
                          fg_color=hexc(ACC[self.cat], 0.32 + 0.05 * (i % 5)), hover_color=hexc(ACC[self.cat], 0.75), command=lambda n=n: self.pick_genre(n)).grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")
    def show_feed(self, genre):
        self.search_active = False
        self.genre = genre; self.back.pack(side="left", before=self.feed_title); self.feed_title.configure(text=f"{genre} · {TAG[self.cat]}" if genre != "All" else TAG[self.cat])
        for w in self.list.winfo_children(): w.destroy()
        self.list.grid_columnconfigure((0, 1), weight=0)
        if self.cat == "music":
            rows = [item for item in self.items if genre == "All" or
                    (genre in {"Bands & Live Shows", "Music Festivals"} and self.music_type_of(item) == genre) or
                    self.genre_of(item) == genre]
        else:
            rows = [item for item in self.items if genre == "All" or self.genre_of(item) == genre]
        rows.sort(key=lambda item: -float(g(item, "score", 0) or 0))
        page_size = 25
        page_count = max(1, (len(rows) + page_size - 1) // page_size)
        self.page = min(max(0, self.page), page_count - 1)
        start = self.page * page_size
        self.shown, self.cards, self.imgs = rows[start:start + page_size], {}, []
        if not rows:
            empty_message = ("No concerts or live music events saved yet.\nAdd your Ticketmaster key on the dashboard and select Find events."
                             if self.cat == "music" else "Nothing here yet.\nAdd titles or run the scraper.")
            ctk.CTkLabel(self.list, text=empty_message, text_color="#888", font=("Segoe UI", 15), wraplength=300).pack(pady=40)
        for n, it in enumerate(self.shown):
            row = ctk.CTkFrame(self.list, fg_color=CARD, corner_radius=14, height=108); row.pack(fill="x", padx=4, pady=5); row.pack_propagate(False)
            im = ctk.CTkImage(art(g(it, "title"), ACC[self.cat], (116, 172)), size=(58, 86)); self.imgs.append(im)
            ctk.CTkLabel(row, text="", image=im).pack(side="left", padx=10, pady=8)
            col = ctk.CTkFrame(row, fg_color="transparent"); col.pack(side="left", fill="both", expand=True, pady=10)
            ctk.CTkLabel(col, text=f"#{start + n + 1}", font=("Segoe UI", 12, "bold"), text_color=hexc(ACC[self.cat]), anchor="w").pack(fill="x")
            title_text = g(it, "title")
            title_font = 17 if len(title_text) < 38 else 15 if len(title_text) < 62 else 13
            subtitle_text = f"{sub_of(it)} · {g(it, 'year')}".strip(" ·")
            title_height = wrapped_height(self.insp, title_text, title_font, 190, True)
            subtitle_height = wrapped_height(self.insp, subtitle_text, 13, 190)
            row_height = max(108, min(210, 38 + title_height + (subtitle_height if subtitle_text else 0) + 22))
            row.configure(height=row_height)
            ctk.CTkLabel(col, text=title_text, font=("Segoe UI", title_font, "bold"), anchor="w", justify="left", wraplength=190, height=title_height).pack(fill="x")
            ctk.CTkLabel(col, text=subtitle_text, font=("Segoe UI", 13), text_color="#9aa0b5", anchor="w", justify="left", wraplength=190, height=subtitle_height).pack(fill="x")
            ctk.CTkLabel(row, text=f"{float(g(it, 'score', 0) or 0):.0f}", width=46, height=46, corner_radius=23, fg_color=hexc(ACC[self.cat], 0.6), font=("Segoe UI", 16, "bold")).pack(side="right", padx=10)
            bind_all(row, lambda e, n=n: self.select(n)); self.cards[n] = row
        if rows:
            controls = ctk.CTkFrame(self.list, fg_color="transparent")
            controls.pack(fill="x", padx=4, pady=(12, 18))
            ctk.CTkButton(controls, text="‹  Previous", width=110, fg_color=CARD, hover_color=HOVER,
                          state="normal" if self.page > 0 else "disabled",
                          command=lambda: self.change_feed_page(-1)).pack(side="left")
            ctk.CTkLabel(controls, text=f"{start + 1}–{min(start + len(self.shown), len(rows))} of {len(rows)} events" if self.cat == "music" else f"{start + 1}–{min(start + len(self.shown), len(rows))} of {len(rows)}",
                         text_color="#9aa0b5").pack(side="left", expand=True)
            ctk.CTkButton(controls, text="Next  ›", width=110, fg_color=CARD, hover_color=HOVER,
                          state="normal" if self.page + 1 < page_count else "disabled",
                          command=lambda: self.change_feed_page(1)).pack(side="right")

    def change_feed_page(self, step):
        self.page += step
        if self.search_active: self.show_search_results()
        else: self.show_feed(self.genre)

    def focus_search(self, _event=None):
        self.search_entry.focus_set(); self.search_entry.select_range(0, "end")
        return "break"

    def schedule_search(self, _event=None):
        if self.search_job:
            try: self.after_cancel(self.search_job)
            except Exception: pass
        self.search_job = self.after(280, self.run_search)

    def run_search(self):
        self.search_job = None
        query = self.search_entry.get().strip()
        if not query:
            self.clear_search(); return
        self.search_query = query
        self.page = 0
        normalized = online._norm(query)
        terms = normalized.split()
        if len(normalized) < 2:
            self.search_results = []
            self.show_search_results("Keep typing to search Spotlight.")
            return
        scope = [self.cat] if self.search_scope.get() == "This section" else list(ACC)
        matches = []
        for category in scope:
            for item in database.load_local_catalog(category):
                metadata = self.meta.get(category, g(item, "title"))
                searchable = online._norm(" ".join((g(item, "title"), sub_of(item), g(item, "description"),
                                                       g(item, "year"), metadata.get("genre", ""), metadata.get("music_genre", ""),
                                                       metadata.get("music_type", ""), metadata.get("music_artist", ""))))
                if not all(term in searchable for term in terms):
                    continue
                title = online._norm(g(item, "title"))
                rank = 100 if title == normalized else 60 if title.startswith(normalized) else 30 if normalized in title else 0
                result = dict(item); result["_search_category"] = category
                matches.append((rank, float(g(item, "score", 0) or 0), category, result))
        matches.sort(key=lambda match: (-match[0], -match[1], g(match[3], "title").casefold()))
        self.search_results = [(category, item) for _rank, _score, category, item in matches]
        self.show_search_results()

    def show_search_results(self, message=None):
        self.search_active = True
        scope_label = "Everywhere" if self.search_scope.get() == "Everywhere" else next((name for key, _icon, name in NAV if key == self.cat), "This section")
        self.feed_title.configure(text=f"Search · {scope_label} ({len(self.search_results)})")
        self.back.pack(side="left", before=self.feed_title)
        for widget in self.list.winfo_children(): widget.destroy()
        self.list.grid_columnconfigure((0, 1), weight=0)
        if message or not self.search_results:
            ctk.CTkLabel(self.list, text=message or "No matches yet. Try another name, artist, venue, or keyword.",
                         text_color="#9aa0b5", font=("Segoe UI", 15), wraplength=300, justify="left").pack(padx=16, pady=32)
            self.shown, self.cards, self.imgs = [], {}, []
            return
        page_size = 25
        page_count = (len(self.search_results) + page_size - 1) // page_size
        self.page = min(max(self.page, 0), page_count - 1)
        start = self.page * page_size
        self.shown = [item for _category, item in self.search_results[start:start + page_size]]
        self.cards, self.imgs = {}, []
        for index, item in enumerate(self.shown):
            category = item["_search_category"]; accent = ACC[category]
            title_text = g(item, "title")
            metadata = self.meta.get(category, title_text)
            title_height = wrapped_height(self.insp, title_text, 15, 220, True)
            subtitle = " · ".join(value for value in (metadata.get("music_artist") or sub_of(item), g(item, "year")) if value)
            subtitle_height = wrapped_height(self.insp, subtitle, 12, 220)
            row_height = max(96, min(180, 34 + title_height + (subtitle_height if subtitle else 0) + 18))
            row = ctk.CTkFrame(self.list, fg_color=CARD, corner_radius=14, height=row_height); row.pack(fill="x", padx=4, pady=4); row.pack_propagate(False)
            image = ctk.CTkImage(art(g(item, "title"), accent, (104, 152)), size=(52, 76)); self.imgs.append(image)
            ctk.CTkLabel(row, text="", image=image).pack(side="left", padx=9, pady=7)
            details = ctk.CTkFrame(row, fg_color="transparent"); details.pack(side="left", fill="both", expand=True, pady=8)
            category_name = next((name for key, _icon, name in NAV if key == category), category.title())
            ctk.CTkLabel(details, text=category_name.upper(), font=("Segoe UI", 10, "bold"), text_color=hexc(accent), anchor="w").pack(fill="x")
            ctk.CTkLabel(details, text=title_text, font=("Segoe UI", 15, "bold"), anchor="w", justify="left", wraplength=220, height=title_height).pack(fill="x")
            ctk.CTkLabel(details, text=subtitle, font=("Segoe UI", 12), text_color="#9aa0b5", anchor="w", justify="left", wraplength=220, height=subtitle_height).pack(fill="x")
            bind_all(row, lambda _event, number=index: self.select(number)); self.cards[index] = row
        controls = ctk.CTkFrame(self.list, fg_color="transparent"); controls.pack(fill="x", padx=4, pady=(12, 18))
        ctk.CTkButton(controls, text="‹  Previous", width=110, fg_color=CARD, hover_color=HOVER, state="normal" if self.page > 0 else "disabled",
                      command=lambda: self.change_feed_page(-1)).pack(side="left")
        ctk.CTkLabel(controls, text=f"{start + 1}–{min(start + len(self.shown), len(self.search_results))} of {len(self.search_results)} matches",
                     text_color="#9aa0b5").pack(side="left", expand=True)
        ctk.CTkButton(controls, text="Next  ›", width=110, fg_color=CARD, hover_color=HOVER, state="normal" if self.page + 1 < page_count else "disabled",
                      command=lambda: self.change_feed_page(1)).pack(side="right")

    def clear_search(self):
        if self.search_job:
            try: self.after_cancel(self.search_job)
            except Exception: pass
            self.search_job = None
        if self.search_entry.get(): self.search_entry.delete(0, "end")
        self.search_query = ""; self.search_results = []; self.search_active = False; self.page = 0
        if hasattr(self, "list") and self.list.winfo_exists(): self.show_genres()

    def back_to_list(self):
        if self.search_active and self.sel is not None:
            self.sel = None; self.sel_cat = None; self.close_bio(); self.show_promo(True)
            self.poster.pack_forget()
            for button in (self.find_btn, self.buy_btn, self.trailer_btn, self.mute_btn): button.pack_forget()
            self.title.configure(text="Search results"); self.meta_lbl.configure(text=""); self.desc.configure(text="")
            for frame in (self.cast_row, self.ev_box, self.about_box):
                for widget in frame.winfo_children(): widget.destroy()
            return
        if self.search_active: self.clear_search()
        else: self.show_genres()

    # ---------- detail page ----------
    def find_video(self, title):
        for ext in ("mp4", "mov", "mkv", "webm"):
            for folder in (VIDEOS, LEGACY_VIDEOS):
                path = os.path.join(folder, slug(title) + "." + ext)
                if os.path.exists(path): return path
        return None
    def find_audio(self, title):
        for stem in (slug(title) + ".audio", slug(title)):
            for ext in (".m4a", ".mp3", ".aac", ".wav", ".flac", ".ogg"):
                for folder in (VIDEOS, LEGACY_VIDEOS):
                    path = os.path.join(folder, stem + ext)
                    if os.path.exists(path): return path
        return None
    def avatar(self, name, size=96):
        pp = os.path.join(PEOPLE, slug(name) + ".jpg"); acc = tuple(70 + (zlib.crc32(name.encode()) >> s) % 150 for s in (0, 8, 16)); S = size * 4
        src = ImageOps.fit(Image.open(pp).convert("RGB"), (S, S), centering=(0.5, 0.2)) if os.path.exists(pp) else art(name, acc, (S, S), True)
        mk = Image.new("L", (S, S), 0); ImageDraw.Draw(mk).ellipse((0, 0, S - 1, S - 1), fill=255); mk = mk.resize((size, size), Image.LANCZOS)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0)); out.paste(src.resize((size, size), Image.LANCZOS).convert("RGBA"), (0, 0), mk)
        return ctk.CTkImage(out, size=(size, size))
    def select(self, n):
        it = self.shown[n]
        category = it.get("_search_category", self.cat)
        if category != self.cat:
            self.cat = category; self.items = list(database.load_local_catalog(category)); self.mark_nav(category)
            name = next(label for key, _icon, label in NAV if key == category)
            self.hero.configure(height=190 if category in {"movies", "tv"} else 150)
            self.hero.play(os.path.join(MEDIA, "ambient", category + ".mp4"), FXK[category], ACC[category], None,
                           (name.upper(), TAG[category]), dim=0.65)
        self.sel = it; self.sel_cat = category; self.close_bio(); self.show_promo(False)
        for k, card in self.cards.items():
            card_category = self.shown[k].get("_search_category", self.cat)
            card.configure(fg_color=hexc(ACC[card_category], 0.35) if k == n else CARD)
        self.render_detail(it); self.fetch_online(it)
        if self.auto_var.get() and self.meta.get(category, g(it, "title")).get("yt_id"): self.play_trailer()
    def render_detail(self, it):
        cat = self.sel_cat; acc = ACC[cat]; title = g(it, "title"); m = self.meta.get(cat, title); city = (self.gate.user or {}).get("city", "") if hasattr(self, "gate") else ""
        vid = m.get("video") if m.get("video") and os.path.exists(m["video"]) else self.find_video(title)
        if cat == "music":
            vid = m.get("music_video") if m.get("music_video") and os.path.exists(m["music_video"]) else vid
            audio = m.get("music_audio") if m.get("music_audio") and os.path.exists(m["music_audio"]) else self.find_audio(title)
        else:
            audio = None
        bp = os.path.join(BACKDROPS, slug(title) + ".jpg"); still = Image.open(bp).convert("RGB") if os.path.exists(bp) and not vid else None
        if cat == "music" and vid:
            self.theater.play(vid, "wave", acc, None, (title, f"MUSIC VIDEO PREVIEW · muted · {sub_of(it)}"), still=None)
        elif cat == "music" and audio:
            self.theater.play_audio(audio, "wave", acc, (title, f"AUDIO PREVIEW · muted · {sub_of(it)}"))
        else:
            self.theater.play(vid, "wave" if cat == "music" else FXK[cat], acc, None,
                              (title, ("TRAILER · muted loop" if vid else ("▶ click to play the trailer" if m.get("yt_id") else ("WAVEFORM" if cat == "music" else "Trailer loading…"))) + f"  ·  {sub_of(it)}"), still=still)
        self.theater.on_click = self.toggle_sound if cat == "music" and self.theater.vlc_on else self.play_trailer if m.get("yt_id") else None
        self.theater.configure(cursor="hand2" if self.theater.on_click else "")
        ps = (300, 300) if cat == "music" else (250, 375); self.poster.configure(image=ctk.CTkImage(art(title, acc, (ps[0] * 2, ps[1] * 2)), size=ps)); self.poster.pack(side="left", anchor="n", padx=(0, 12), before=self.theater)
        for b in (self.find_btn, self.trailer_btn, self.mute_btn, self.buy_btn): b.pack_forget()
        if m.get("yt_id"): self.trailer_btn.pack(side="left", padx=8)
        else: self.find_btn.pack(side="left", padx=8)
        if self.theater.vlc_on: self.mute_btn.configure(text="🔊  Unmute" if self.theater.muted else "🔇  Mute"); self.mute_btn.pack(side="left", padx=8)
        if m.get("buy_url"): self.buy_btn.configure(text="🛒  " + m.get("buy_label", "Buy / Rent")); self.buy_btn.pack(side="left", padx=8)
        extra = "   •   ".join(x for x in (m.get("rated"), m.get("runtime")) if x)
        lead = ("🤝 Community listing   •   " if m.get("community") else "") + f"📅 {g(it, 'recent_shown')}" if cat in UNIT else f"★ {g(it, 'score')}   •   First: {g(it, 'first_shown')}   •   Latest: {g(it, 'recent_shown')}"
        self.title.configure(text=f"{title} ({g(it, 'year')})" if g(it, "year") else title)
        self.meta_lbl.configure(text=f"{sub_of(it)}   •   {self.genre_of(it)}   •   {lead}" + (f"   •   {extra}" if extra else ""))
        self.desc.configure(text=g(it, "description")); self.render_cast(it)
        for w in self.about_box.winfo_children(): w.destroy()
        about = m.get("about")
        detail_width = max(180, self.insp._reverse_widget_scaling(self.insp.winfo_width()) - 40)
        self.about_label = ctk.CTkLabel(self.about_box, text=about or "Extended details load from the web the first time you open a title (needs internet).", font=("Segoe UI", 15), text_color="#cfd3e0" if about else "#888",
                                         justify="left", anchor="w", wraplength=detail_width)
        self.about_label.pack(fill="x")
        if m.get("about_url"): ctk.CTkButton(self.about_box, text="Read more on Wikipedia", fg_color=CARD, hover_color=HOVER, command=lambda u=m["about_url"]: webbrowser.open(u)).pack(anchor="w", pady=6)
        if m.get("tmdb_url"):
            ctk.CTkButton(self.about_box, text="Full cast, crew & details on TMDB", fg_color=CARD, hover_color=HOVER, command=lambda u=m["tmdb_url"]: webbrowser.open(u)).pack(anchor="w", pady=2)
            ctk.CTkLabel(self.about_box, text="This product uses the TMDB API but is not endorsed or certified by TMDB.", text_color="#777", font=("Segoe UI", 11)).pack(anchor="w")
        for w in self.ev_box.winfo_children(): w.destroy()
        self.event_detail_labels = []
        evs = database.load_details(g(it, "id"))[1]
        if not evs:
            ctk.CTkLabel(self.ev_box, text="No saved dates yet. Search ticket vendors:", text_color="#888").pack(anchor="w"); self.vendor_row(self.ev_box, title, cat)
        for ev in evs:
            r = ctk.CTkFrame(self.ev_box, fg_color=CARD, corner_radius=12); r.pack(fill="x", pady=4)
            event_width = max(180, self.insp._reverse_widget_scaling(self.insp.winfo_width()) - 390)
            event_text = f"📍  {g(ev, 'venue_name')}\n{g(ev, 'event_time')}  ·  {g(ev, 'location_details')}"
            event_label = ctk.CTkLabel(r, text=event_text, font=("Segoe UI", 15), justify="left", anchor="w", wraplength=event_width,
                                       height=wrapped_height(self.insp, event_text, 15, event_width))
            event_label.pack(side="left", fill="x", expand=True, padx=14, pady=10); self.event_detail_labels.append(event_label)
            right = ctk.CTkFrame(r, fg_color="transparent"); right.pack(side="right", padx=10); real = g(ev, "purchase_url")
            if real: ctk.CTkButton(right, text="🎟  Reserve / Buy Tickets", fg_color="#1E7A34", hover_color="#27a046", command=lambda u=real: webbrowser.open(u)).pack(side="left", padx=3)
            for name, url in events.vendor_links(f"{title} {g(ev, 'venue_name')}" if cat != "sports" else title, cat)[: (2 if real else 3)]:
                ctk.CTkButton(right, text=name, width=90, fg_color="#2a2a3c" if real else "#1E7A34", hover_color=HOVER, command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=3)
        if self.tmdb_detail_image is not None and cat in {"movies", "tv"}:
            self.tmdb_notes_mark.pack(fill="x", pady=(0, 6), before=self.notes)
        else:
            self.tmdb_notes_mark.pack_forget()
        self.notes.delete("1.0", "end"); self.notes.insert("1.0", g(it, "user_notes")); self.on_resize()
    def vendor_row(self, parent, query, cat):
        r = ctk.CTkFrame(parent, fg_color="transparent"); r.pack(anchor="w", pady=4)
        for name, url in events.vendor_links(query, cat): ctk.CTkButton(r, text=f"🎟  {name}", width=120, fg_color="#1E7A34", hover_color="#27a046", command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=4)
    def toggle_sound(self):
        self.mute_btn.configure(text="🔊  Unmute" if self.theater.toggle_mute() else "🔇  Mute")
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
        music_media_due = cat == "music" and not mm.get("music_media_v1") and time.time() - mm.get("music_media_try", 0) > 86400
        need = (not mm.get("online_v3") and time.time() - mm.get("online_try", 0) > 86400 * 3) or bool(key and cat in ("movies", "tv") and not mm.get("tmdb_id") and time.time() - mm.get("tmdb_try", 0) > 3600) or music_media_due
        rows = database.load_details(iid)[0][:8]
        fresh = [g(x, "name") for x in rows if not os.path.exists(os.path.join(PEOPLE, slug(g(x, "name")) + ".jpg")) and online.cached_person(PEOPLE, g(x, "name")) is None]
        if not need and not fresh: return
        def work():
            res, ppl = None, False
            try:
                if need: res = online.fetch(cat, title, sub, year, POSTERS, VIDEOS, slug(title), key, BACKDROPS, PEOPLE, artist=mm.get("music_artist", "") if cat == "music" else "")
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
        else:
            self.meta.put(cat, title, online_try=time.time(), music_media_try=time.time())
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
        self.meta.save()
        if self.cat == "music" and self.sel is None:
            self.items = list(database.load_local_catalog("music"))
        self.gate.show_dashboard(f"Done: {res['music']} concerts/music events, {res['sports']} sports, and {res['festivals']} festivals and fairs found {search_label}.")
    def sync_tmdb(self, say, token):
        """Refresh the movie and on-air TV catalogs from TMDB in the background."""
        if not token:
            return say("Paste your TMDB API Read Access Token, then choose Update All.")
        say("Updating currently playing movies and on-air TV from TMDB…")
        def work():
            try:
                catalogs = online.tmdb_catalog(token)
            except urllib.error.HTTPError as exc:
                message = "TMDB rejected the token. Check it in the TMDB key field and try again." if exc.code in (401, 403) else f"TMDB update failed (HTTP {exc.code})."
                return self.uiq.put((say, (message,)))
            except Exception as exc:
                return self.uiq.put((say, (f"TMDB update failed: {exc}",)))
            for cat in ("movies", "tv"):
                for result in catalogs.get(cat, []):
                    poster_path = os.path.join(POSTERS, slug(result["title"]) + ".jpg")
                    if result["poster"] and not os.path.exists(poster_path):
                        try: online._save(result["poster"], poster_path)
                        except Exception: pass
            self.uiq.put((self.apply_tmdb, (catalogs, say)))
        threading.Thread(target=work, daemon=True).start()
    def apply_tmdb(self, catalogs, say=None):
        now = int(time.time()); added = {"movies": 0, "tv": 0}; updated = {"movies": 0, "tv": 0}
        for cat in ("movies", "tv"):
            existing = {g(item, "title").casefold(): item for item in database.load_local_catalog(cat)}
            for result in catalogs.get(cat, []):
                title = result["title"]
                old = existing.get(title.casefold())
                sub = g(old, "sub") or ("Now playing" if cat == "movies" else "Currently airing")
                database.save_media_item(cat, {
                    "title": title, "sub": sub, "year": result["year"], "url": result["url"],
                    "score": result["score"], "desc": result["overview"],
                    "first_shown": result["date"] or ("Now playing" if cat == "movies" else "Currently airing"),
                    "recent_shown": "Now playing" if cat == "movies" else "Currently airing", "srcs": ["TMDB"],
                })
                if old: updated[cat] += 1
                else: added[cat] += 1
                metadata = self.meta.d.setdefault(f"{cat}|{title}", {})
                metadata.update({"genre": result["genre"], "tmdb_id": result["id"], "tmdb_url": result["url"], "tmdb_catalog": True, "tmdb_catalog_updated": now})
                for art_key in [key for key in _ART if key[0] == title]: del _ART[art_key]
        self.meta.save()
        movie_total = len(database.load_local_catalog("movies")); tv_total = len(database.load_local_catalog("tv"))
        details = f"TMDB updated: {added['movies']} new movies, {updated['movies']} refreshed; {added['tv']} new TV shows, {updated['tv']} refreshed."
        if say: say(f"{details} Current catalog totals: {movie_total} movies, {tv_total} TV shows.")
        if self.gate.winfo_ismapped(): self.gate.show_dashboard(f"{details} Full cast, trailers, and extended details load when you open a title.")
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
