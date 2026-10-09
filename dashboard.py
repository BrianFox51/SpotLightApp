"""Spotlight startup gate: Mythic Mask Works banner, sign in / create account / guest, then the Dashboard with live stats.
Put the banner PNG (Mythic_Mask_Works_promotional_banner2.png) next to main.py, or in its media/ or assets/ folder."""
import os, glob, json, urllib.request, webbrowser
import customtkinter as ctk
from PIL import Image
import database
import events

BG, PANEL, CARD, HOVER, GOLD = "#0b0b11", "#12121a", "#1a1a26", "#28283e", "#c9a45c"
SITE = "https://mythicmaskworks.com"
LOGO_BBOX = (38, 42, 1219, 1122)     # visible area of LightWave_logo.png
WORDMARK = (30, 655, 1225, 880)      # the "SPOTLIGHT" lettering inside it


def load_logo(base):
    """The official SpotLight logo (LightWave_logo.png) as RGBA, or None. Looked for next to main.py, in media/ or assets/."""
    for d in (base, os.path.join(base, "media"), os.path.join(base, "assets")):
        for pat in ("LightWave_logo*", "spotlight_logo*"):
            hits = [h for h in glob.glob(os.path.join(d, pat)) if h.lower().endswith((".png", ".webp"))]
            if hits:
                try: return Image.open(hits[0]).convert("RGBA")
                except Exception: pass
    return None


def trim_logo(img): return img.crop(LOGO_BBOX) if img is not None else None


def find_banner(base):
    for d in (base, os.path.join(base, "media"), os.path.join(base, "assets")):
        for pat in ("Mythic_Mask_Works*", "mythic*mask*banner*"):
            hits = [h for h in glob.glob(os.path.join(d, pat)) if h.lower().endswith((".png", ".jpg", ".jpeg"))]
            if hits: return hits[0]
    return None


def lookup_zip(z):
    """US ZIP -> (city, state, lat, lng). Needs internet; returns blanks offline."""
    try:
        with urllib.request.urlopen(f"https://api.zippopotam.us/us/{z}", timeout=4) as r: p = json.load(r)["places"][0]
        return p["place name"], p["state abbreviation"], float(p["latitude"]), float(p["longitude"])
    except Exception:
        return "", "", None, None


class Gate(ctk.CTkFrame):
    def __init__(s, app, base):
        super().__init__(app, fg_color=BG, corner_radius=0)
        s.app, s.user, s.imgs, s.banner, s.logo = app, None, [], find_banner(base), trim_logo(load_logo(base))
        s.place(x=0, y=0, relwidth=1, relheight=1); s.show_login()

    def clear(s):
        for w in s.winfo_children(): w.destroy()
        s.imgs.clear(); s.place(x=0, y=0, relwidth=1, relheight=1); s.lift()

    def logo_label(s, w):
        if s.logo is None: ctk.CTkLabel(s, text="SPOTLIGHT", font=("Segoe UI", 40, "bold")).pack(pady=(24, 4)); return
        ci = ctk.CTkImage(s.logo, size=(w, int(w * s.logo.height / s.logo.width))); s.imgs.append(ci); ctk.CTkLabel(s, text="", image=ci).pack(pady=(10, 0))

    def header(s):
        s.logo_label(270)
        if s.banner:
            im = Image.open(s.banner).convert("RGB"); w = 300; h = int(w * im.height / im.width)
            ci = ctk.CTkImage(im, size=(w, h)); s.imgs.append(ci); ctk.CTkLabel(s, text="", image=ci).pack(pady=(8, 0))
        else:
            ctk.CTkLabel(s, text="MYTHIC MASK WORKS", font=("Segoe UI", 20, "bold"), text_color=GOLD).pack(pady=(8, 0))
        ctk.CTkButton(s, text="mythicmaskworks.com   ·   free app", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      font=("Segoe UI", 14, "bold"), command=lambda: webbrowser.open(SITE)).pack()

    # ---------- sign in / create account / guest ----------
    def show_login(s):
        s.clear(); s.header()
        tabs = ctk.CTkTabview(s, width=460, height=250, fg_color=PANEL); tabs.pack(pady=8)
        si, su = tabs.add("Sign In"), tabs.add("Create Account")
        u1 = ctk.CTkEntry(si, placeholder_text="Username", width=320); u1.pack(pady=(14, 6))
        p1 = ctk.CTkEntry(si, placeholder_text="Password", show="•", width=320); p1.pack(pady=6)
        ctk.CTkButton(si, text="Sign In", width=320, command=lambda: s.do_login(u1.get(), p1.get())).pack(pady=10)
        p1.bind("<Return>", lambda e: s.do_login(u1.get(), p1.get()))
        u2 = ctk.CTkEntry(su, placeholder_text="Username (3+ characters)", width=320); u2.pack(pady=(10, 4))
        p2 = ctk.CTkEntry(su, placeholder_text="Password (6+ characters)", show="•", width=320); p2.pack(pady=4)
        z2 = ctk.CTkEntry(su, placeholder_text="ZIP code (finds events near you)", width=320); z2.pack(pady=4)
        ctk.CTkButton(su, text="Create Account", width=320, command=lambda: s.do_signup(u2.get(), p2.get(), z2.get())).pack(pady=10)
        s.err = ctk.CTkLabel(s, text="", text_color="#ff6b6b", font=("Segoe UI", 13)); s.err.pack()
        ctk.CTkButton(s, text="Continue as guest", fg_color=CARD, hover_color=HOVER, command=s.guest).pack(pady=6)

    def do_login(s, u, p):
        user = database.verify_user(u, p) if u.strip() and p else None
        if not user: return s.err.configure(text="Wrong username or password.")
        s.user = user; s.show_dashboard()

    def do_signup(s, u, p, z):
        u, z = u.strip(), z.strip()
        if len(u) < 3: return s.err.configure(text="Username needs at least 3 characters.")
        if len(p) < 6: return s.err.configure(text="Password needs at least 6 characters.")
        if z and not (z.isdigit() and len(z) == 5): return s.err.configure(text="Enter a 5-digit US ZIP code, or leave it blank.")
        city, state, lat, lng = lookup_zip(z) if z else ("", "", None, None)
        ok, msg = database.create_user(u, p, z, city, state, lat, lng)
        if not ok: return s.err.configure(text=msg)
        s.user = database.verify_user(u, p); s.show_dashboard()

    def guest(s):
        s.user = {"display_name": "Guest", "city": "", "state": "", "zip": ""}; s.show_dashboard()

    # ---------- dashboard ----------
    def say(s, msg):
        try: s.status.configure(text=msg)
        except Exception: pass

    def show_dashboard(s, status=""):
        s.clear()
        u = s.user or {"display_name": "Guest", "city": "", "state": ""}; city, state = u.get("city") or "", u.get("state") or ""
        st = database.dashboard_stats(city, state); c = st["cats"]
        s.logo_label(190)
        ctk.CTkLabel(s, text=f"Welcome, {u.get('display_name', 'Guest')}", font=("Segoe UI", 20), text_color=GOLD).pack()
        where = ", ".join(x for x in (city, state) if x) or "No location set: create an account with a ZIP code to see what's near you"
        ctk.CTkLabel(s, text="📍  " + where, text_color="#9aa0b5", font=("Segoe UI", 14)).pack(pady=(2, 22))
        cards = [("Titles found", st["total"]), ("🎵 Music", c.get("music", 0)), ("🎬 Movies", c.get("movies", 0)), ("📺 TV", c.get("tv", 0)),
                 ("🎮 Games", c.get("games", 0)), ("🏆 Sports", c.get("sports", 0)), ("🎪 Festivals", c.get("festivals", 0)), ("📍 Local events saved", st["events"]),
                 (f"Titles near {city}" if city else "Titles near you", st["near_city"] if city else "-"),
                 (f"Titles in {state}" if state else "Titles in your state", st["near_state"] if state else "-")]
        grid = ctk.CTkFrame(s, fg_color="transparent"); grid.pack()
        for i, (label, val) in enumerate(cards):
            f = ctk.CTkFrame(grid, width=200, height=110, fg_color=CARD, corner_radius=16); f.grid(row=i // 5, column=i % 5, padx=8, pady=8); f.pack_propagate(False)
            ctk.CTkLabel(f, text=str(val), font=("Segoe UI", 34, "bold"), text_color=GOLD).pack(pady=(16, 0))
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 13), text_color="#9aa0b5").pack()
        cfg = events.load_cfg(); live = ctk.CTkFrame(s, fg_color=CARD, corner_radius=14); live.pack(pady=(6, 0))
        ctk.CTkLabel(live, text="🌐  Live events: sports, festivals and music dates (Ticketmaster)", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        area_row = ctk.CTkFrame(live, fg_color="transparent"); area_row.pack(anchor="w", padx=14, pady=(6, 2))
        ctk.CTkLabel(area_row, text="Search area", text_color="#9aa0b5").pack(side="left", padx=(0, 8))
        area_choices = ["Nearby (75 mi)"]
        state_choice = f"All of {state}" if state else ""
        if state_choice: area_choices.append(state_choice)
        area = ctk.StringVar(value=area_choices[0])
        ctk.CTkOptionMenu(area_row, values=area_choices, variable=area, width=170).pack(side="left")
        lr = ctk.CTkFrame(live, fg_color="transparent"); lr.pack(padx=14, pady=(0, 4))
        key = ctk.CTkEntry(lr, width=300, show="•", placeholder_text="Paste your free Ticketmaster API key"); key.pack(side="left", padx=(0, 6))
        if cfg.get("ticketmaster_key"): key.insert(0, cfg["ticketmaster_key"])
        lr2 = ctk.CTkFrame(live, fg_color="transparent"); lr2.pack(padx=14, pady=(0, 4))
        tkey = ctk.CTkEntry(lr2, width=300, show="•", placeholder_text="Paste your free TMDB key (movie & TV cast, posters, trailers)"); tkey.pack(side="left", padx=(0, 6))
        if cfg.get("tmdb_key"): tkey.insert(0, cfg["tmdb_key"])
        def save_key(): events.save_cfg({**events.load_cfg(), "ticketmaster_key": key.get().strip(), "tmdb_key": tkey.get().strip()})
        ctk.CTkButton(lr2, text="Save keys", width=110, command=lambda: (save_key(), s.say("Keys saved. Open a movie or show to load its full cast."))).pack(side="left", padx=4)
        ctk.CTkButton(lr2, text="Get a free key", fg_color="transparent", hover_color=HOVER, text_color=GOLD, command=lambda: webbrowser.open("https://www.themoviedb.org/settings/api")).pack(side="left")
        ctk.CTkButton(lr, text="🔄  Find events", command=lambda: (save_key(), s.app.sync_events(s.say, "state" if area.get() == state_choice and state_choice else "nearby"))).pack(side="left", padx=4)
        ctk.CTkButton(lr, text="Get a free key", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      command=lambda: webbrowser.open("https://developer.ticketmaster.com/products-and-docs/apis/getting-started/")).pack(side="left")
        s.status = ctk.CTkLabel(live, text=status or "Keys stay on this PC. Movie/TV data: TMDB (this product uses the TMDB API but is not endorsed or certified by TMDB).", text_color="#9aa0b5", font=("Segoe UI", 12)); s.status.pack(pady=(0, 10))
        row = ctk.CTkFrame(s, fg_color="transparent"); row.pack(pady=18)
        ctk.CTkButton(row, text="Enter Spotlight  ▶", width=220, height=46, font=("Segoe UI", 17, "bold"), command=s.place_forget).pack(side="left", padx=8)
        ctk.CTkButton(row, text="📣  Promote an event", width=190, height=46, fg_color="#9b6a1c", hover_color="#c48a2a", font=("Segoe UI", 15, "bold"), command=s.app.open_promote).pack(side="left", padx=8)
        ctk.CTkButton(row, text="🔄 Community", width=120, height=46, fg_color=CARD, hover_color=HOVER, command=lambda: s.app.sync_community(s.say)).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Sign out", width=100, height=46, fg_color=CARD, hover_color=HOVER, command=s.sign_out).pack(side="left", padx=8)

    def sign_out(s):
        s.user = None; s.show_login()
