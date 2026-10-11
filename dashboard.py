"""Spotlight startup gate: Mythic Mask Works banner, sign in / create account / guest, then the Dashboard with live stats.
Put the banner PNG (Mythic_Mask_Works_promotional_banner2.png) next to main.py, or in its media/ or assets/ folder."""
import os, glob, json, urllib.request, webbrowser
import customtkinter as ctk
from PIL import Image
import database
import events
import local_secrets

BG, PANEL, CARD, HOVER, GOLD = "#0b0b11", "#12121a", "#1a1a26", "#28283e", "#c9a45c"
SITE = "https://mythicmaskworks.com"
LOGO_BBOX = (38, 42, 1219, 1122)     # visible area of LightWave_logo.png
WORDMARK = (30, 655, 1225, 880)      # the "SPOTLIGHT" lettering inside it

API_FIELDS = (
    ("ticketmaster_key", "Ticketmaster Discovery", "API key · live events", "https://developer.ticketmaster.com/products-and-docs/apis/getting-started/", "active"),
    ("tmdb_key", "TMDB", "Read Access Token or v3 API key · movies and TV", "https://www.themoviedb.org/settings/api", "active"),
    ("watchmode_key", "Watchmode", "API key · US streaming catalog and availability", "https://api.watchmode.com/", "active"),
    ("igdb_client_id", "IGDB / Twitch Client ID", "Client ID · popular and upcoming game catalog", "https://dev.twitch.tv/console/apps", "active"),
    ("igdb_client_secret", "IGDB / Twitch Client Secret", "Client secret · keep private; used to request IGDB access", "https://dev.twitch.tv/console/apps", "active"),
    ("spotify_client_id", "Spotify (planned)", "Client ID · optional future music integration", "https://developer.spotify.com/dashboard", "planned"),
    ("spotify_client_secret", "Spotify (planned)", "Client secret · optional future music integration", "https://developer.spotify.com/dashboard", "planned"),
    ("youtube_api_key", "YouTube Data API (optional)", "API key · not currently used by Spotlight", "https://console.cloud.google.com/", "planned"),
)


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


def load_tmdb_logo(base, filename):
    """Load an owner-supplied TMDB PNG and trim transparent padding for UI display."""
    path = os.path.join(base, "media", "tmdb", filename)
    try:
        image = Image.open(path).convert("RGBA")
        bounds = image.getchannel("A").getbbox()
        return image.crop(bounds) if bounds else None
    except (OSError, ValueError):
        return None


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
        s.refreshing, s.refresh_jobs_left = False, 0
        s.refresh_banner, s.refresh_controls = None, []
        s.tmdb_footer_logo = load_tmdb_logo(base, "tmdb_footer.png")
        s.place(x=0, y=0, relwidth=1, relheight=1); s.show_login()

    def set_refreshing(s, active, jobs=0):
        """Show refresh progress and temporarily disable dashboard navigation/actions."""
        s.refreshing = bool(active)
        s.refresh_jobs_left = jobs if active else 0
        if s.refresh_banner is not None and s.refresh_banner.winfo_exists():
            if active:
                s.refresh_banner.pack(pady=(0, 12))
            else:
                s.refresh_banner.pack_forget()
        for widget, ready_state in s.refresh_controls:
            try:
                widget.configure(state="disabled" if active else ready_state)
            except Exception:
                pass

    def refresh_job_finished(s):
        """Release dashboard controls only after each source refresh has returned."""
        if not s.refreshing:
            return
        s.refresh_jobs_left = max(0, s.refresh_jobs_left - 1)
        if s.refresh_jobs_left == 0:
            s.set_refreshing(False)
            s.update_dashboard_stats()
            s.say("Refresh complete.")

    def clear(s):
        for w in s.winfo_children(): w.destroy()
        s.imgs.clear(); s.place(x=0, y=0, relwidth=1, relheight=1); s.lift()
        # Keep the whole gate usable on high-DPI screens with limited vertical space.
        s.page = ctk.CTkScrollableFrame(s, fg_color=BG, corner_radius=0)
        s.page.pack(fill="both", expand=True)

    def logo_label(s, w):
        if s.logo is None: ctk.CTkLabel(s.page, text="SPOTLIGHT", font=("Segoe UI", 40, "bold")).pack(pady=(24, 4)); return
        ci = ctk.CTkImage(s.logo, size=(w, int(w * s.logo.height / s.logo.width))); s.imgs.append(ci); ctk.CTkLabel(s.page, text="", image=ci).pack(pady=(10, 0))

    def header(s):
        s.logo_label(270)

    def sponsor_footer(s, parent):
        if s.banner:
            im = Image.open(s.banner).convert("RGB"); w = 300; h = int(w * im.height / im.width)
            ci = ctk.CTkImage(im, size=(w, h)); s.imgs.append(ci); ctk.CTkLabel(parent, text="", image=ci).pack(pady=(18, 0))
        else:
            ctk.CTkLabel(parent, text="MYTHIC MASK WORKS", font=("Segoe UI", 20, "bold"), text_color=GOLD).pack(pady=(18, 0))
        ctk.CTkButton(parent, text="mythicmaskworks.com   ·   free app", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      font=("Segoe UI", 14, "bold"), command=lambda: webbrowser.open(SITE)).pack(pady=(2, 18))
        if s.tmdb_footer_logo is not None:
            width = 250
            image = ctk.CTkImage(s.tmdb_footer_logo, size=(width, max(1, round(width * s.tmdb_footer_logo.height / s.tmdb_footer_logo.width))))
            s.imgs.append(image)
            ctk.CTkLabel(parent, text="", image=image).pack(pady=(0, 16))

    # ---------- sign in / create account / guest ----------
    def show_login(s):
        s.clear(); s.header(); p=s.page
        tabs = ctk.CTkTabview(p, width=460, height=250, fg_color=PANEL); tabs.pack(pady=8)
        si, su = tabs.add("Sign In"), tabs.add("Create Account")
        cfg = events.load_cfg()
        u1 = ctk.CTkEntry(si, placeholder_text="Username", width=320); u1.pack(pady=(14, 6))
        remembered_user = cfg.get("remembered_username", "")
        if remembered_user: u1.insert(0, remembered_user)
        p1 = ctk.CTkEntry(si, placeholder_text="Password", show="•", width=320); p1.pack(pady=6)
        remember = ctk.BooleanVar(value=cfg.get("remember_me", True))
        remembered_password = local_secrets.unprotect_text(cfg.get("remembered_password_dpapi", ""))
        if remember.get() and remembered_password: p1.insert(0, remembered_password)
        ctk.CTkCheckBox(si, text="Remember password on this PC (securely)", variable=remember).pack(anchor="w", padx=70, pady=(2, 2))
        ctk.CTkButton(si, text="Sign In", width=320, command=lambda: s.do_login(u1.get(), p1.get(), remember.get())).pack(pady=8)
        p1.bind("<Return>", lambda e: s.do_login(u1.get(), p1.get(), remember.get()))
        recovery = ctk.CTkFrame(si, fg_color="transparent"); recovery.pack(pady=(0, 4))
        ctk.CTkButton(recovery, text="Forgot username?", width=130, height=24, fg_color="transparent", hover_color=HOVER,
                      text_color="#78aef5", command=lambda: s.show_recovery_message("Username recovery is not set up yet. You can continue as a guest while we add account recovery.")).pack(side="left", padx=3)
        ctk.CTkButton(recovery, text="Forgot password?", width=130, height=24, fg_color="transparent", hover_color=HOVER,
                      text_color="#78aef5", command=lambda: s.show_recovery_message("Password reset is not set up yet. Passwords are stored as secure hashes and cannot be recovered; reset support will be added later.")).pack(side="left", padx=3)
        u2 = ctk.CTkEntry(su, placeholder_text="Username (3+ characters)", width=320); u2.pack(pady=(10, 4))
        p2 = ctk.CTkEntry(su, placeholder_text="Password (6+ characters)", show="•", width=320); p2.pack(pady=4)
        z2 = ctk.CTkEntry(su, placeholder_text="ZIP code (finds events near you)", width=320); z2.pack(pady=4)
        ctk.CTkButton(su, text="Create Account", width=320, command=lambda: s.do_signup(u2.get(), p2.get(), z2.get())).pack(pady=10)
        s.err = ctk.CTkLabel(p, text="", text_color="#ff6b6b", font=("Segoe UI", 13)); s.err.pack()
        ctk.CTkButton(p, text="Continue as guest", fg_color=CARD, hover_color=HOVER, command=s.guest).pack(pady=6)
        s.sponsor_footer(p)

    def show_recovery_message(s, message):
        try: s.err.configure(text=message)
        except Exception: pass

    def remember_credentials(s, username, password, enabled):
        cfg = events.load_cfg()
        cfg["remember_me"] = bool(enabled)
        cfg["remembered_username"] = username.strip() if username.strip() else ""
        protected = local_secrets.protect_text(password) if enabled else None
        if protected:
            cfg["remembered_password_dpapi"] = protected
        else:
            cfg.pop("remembered_password_dpapi", None)
        events.save_cfg(cfg)

    def do_login(s, u, p, remember=True):
        user = database.verify_user(u, p) if u.strip() and p else None
        if not user: return s.err.configure(text="Wrong username or password.")
        s.remember_credentials(u, p, remember)
        s.user = user; s.show_dashboard()

    def do_signup(s, u, p, z):
        u, z = u.strip(), z.strip()
        if len(u) < 3: return s.err.configure(text="Username needs at least 3 characters.")
        if len(p) < 6: return s.err.configure(text="Password needs at least 6 characters.")
        if z and not (z.isdigit() and len(z) == 5): return s.err.configure(text="Enter a 5-digit US ZIP code, or leave it blank.")
        city, state, lat, lng = lookup_zip(z) if z else ("", "", None, None)
        ok, msg = database.create_user(u, p, z, city, state, lat, lng)
        if not ok: return s.err.configure(text=msg)
        s.user = database.verify_user(u, p)
        s.remember_credentials(u, p, True)
        s.show_dashboard()

    def guest(s):
        s.user = {"display_name": "Guest", "city": "", "state": "", "zip": ""}; s.show_dashboard()

    # ---------- dashboard ----------
    def say(s, msg):
        try: s.status.configure(text=msg)
        except Exception: pass

    def show_dashboard(s, status=""):
        s.clear(); p=s.page
        u = s.user or {"display_name": "Guest", "city": "", "state": ""}; city, state = u.get("city") or "", u.get("state") or ""
        st = database.dashboard_stats(city, state, u.get("username") or "__guest__"); c = st["cats"]
        s.logo_label(190)
        ctk.CTkLabel(p, text=f"Welcome, {u.get('display_name', 'Guest')}", font=("Segoe UI", 20), text_color=GOLD).pack()
        where = ", ".join(x for x in (city, state) if x) or "No location set: create an account with a ZIP code to see what's near you"
        ctk.CTkLabel(p, text="📍  " + where, text_color="#9aa0b5", font=("Segoe UI", 14)).pack(pady=(2, 22))
        s.refresh_banner = ctk.CTkLabel(p, text="⏳  Refreshing Spotlight data… Please wait. Dashboard actions will be available when all updates finish.",
                                        fg_color="#42351d", text_color="#f0cf78", corner_radius=10,
                                        font=("Segoe UI", 14, "bold"), padx=16, pady=11, wraplength=900)
        if s.refreshing: s.refresh_banner.pack(pady=(0, 12))
        dashboard_actions = ctk.CTkFrame(p, fg_color="transparent"); dashboard_actions.pack(pady=(0, 18))
        cards = [("Titles found", st["total"]), ("🎵 Music", c.get("music", 0)), ("🎬 Movies", c.get("movies", 0)), ("📺 TV", c.get("tv", 0)),
                 ("🎮 Games", c.get("games", 0)), ("🏆 Sports", c.get("sports", 0)), ("🎪 Festivals", c.get("festivals", 0)), ("📍 Local events saved", st["events"]),
                 ("⭐ Favorites", st["favorites"]),
                 (f"Titles in {state}" if state else "Titles in your state", st["near_state"] if state else "-")]
        grid = ctk.CTkFrame(p, fg_color="transparent"); grid.pack()
        s.stats_value_labels = []
        for i, (label, val) in enumerate(cards):
            f = ctk.CTkFrame(grid, width=200, height=110, fg_color=CARD, corner_radius=16); f.grid(row=i // 5, column=i % 5, padx=8, pady=8); f.pack_propagate(False)
            value_label = ctk.CTkLabel(f, text=str(val), font=("Segoe UI", 34, "bold"), text_color=GOLD); value_label.pack(pady=(16, 0))
            s.stats_value_labels.append(value_label)
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 13), text_color="#9aa0b5").pack()
        cfg = events.load_cfg(); live = ctk.CTkFrame(p, fg_color=CARD, corner_radius=14); live.pack(pady=(6, 0))
        def saved_api_value(name, source):
            if name == "igdb_client_secret":
                return local_secrets.unprotect_text(source.get("igdb_client_secret_dpapi", "")) or source.get(name, "")
            return source.get(name, "")
        ctk.CTkLabel(live, text="🌐  Spotlight data sources", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        area_row = ctk.CTkFrame(live, fg_color="transparent"); area_row.pack(anchor="w", padx=14, pady=(6, 2))
        ctk.CTkLabel(area_row, text="Search area", text_color="#9aa0b5").pack(side="left", padx=(0, 8))
        state_choice = f"All of {state}" if state else "Statewide (add a ZIP code to your account)"
        area_choices = [state_choice]
        area = ctk.StringVar(value=area_choices[0])
        area_selector = ctk.CTkOptionMenu(area_row, values=area_choices, variable=area, width=210,
                                          state="normal" if state else "disabled")
        area_selector.pack(side="left")
        def refresh_all():
            if s.refreshing: return
            save_api_keys()
            s.refresh_controls = [(area_selector, "normal" if state else "disabled"), (refresh_button, "normal")]
            s.refresh_controls.extend((button, "normal") for button in s.dashboard_action_buttons)
            s.set_refreshing(True, jobs=5)
            current = events.load_cfg()
            report = lambda key, state, message: s.app.uiq.put((s.update_api_status, (key, state, message)))
            done = s.refresh_job_finished
            def start_refresh(job, *args):
                try: job(*args, done)
                except Exception as exc:
                    s.say(f"A refresh job could not start: {exc}")
                    done()
            start_refresh(s.app.sync_tmdb, s.say, current.get("tmdb_key", ""), report)
            start_refresh(s.app.sync_events, s.say, "state", report)
            start_refresh(s.app.sync_ohio_schedules, s.say)
            start_refresh(s.app.sync_watchmode, s.say, current.get("watchmode_key", ""), report)
            start_refresh(s.app.sync_igdb, s.say, current.get("igdb_client_id", ""), saved_api_value("igdb_client_secret", current), report)

        refresh_button = ctk.CTkButton(area_row, text="🔄  Refresh", width=125, command=refresh_all)
        refresh_button.pack(side="left", padx=(10, 0))

        manager_head = ctk.CTkFrame(live, fg_color="transparent"); manager_head.pack(fill="x", padx=14, pady=(6, 2))
        manager = ctk.CTkScrollableFrame(live, fg_color=PANEL, corner_radius=10, width=560, height=255)
        key_entries = {}
        s.api_status_widgets = {}
        show_keys = False
        for api_key, label, hint, link, status_kind in API_FIELDS:
            api_row = ctk.CTkFrame(manager, fg_color="transparent"); api_row.pack(fill="x", padx=6, pady=4)
            left = ctk.CTkFrame(api_row, fg_color="transparent"); left.pack(side="left", fill="x", expand=True)
            suffix = " · planned" if status_kind == "planned" else ""
            ctk.CTkLabel(left, text=label + suffix, font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(left, text=hint, text_color="#9aa0b5", font=("Segoe UI", 10), anchor="w").pack(fill="x")
            status = cfg.get("api_statuses", {}).get(api_key, {})
            state = status.get("state", "not_set" if not saved_api_value(api_key, cfg) else "not_checked")
            status_color = {"ok": "#45b86b", "bad": "#df4c55", "not_set": "#a8aab2", "not_checked": "#a8aab2", "planned": "#a8aab2"}.get(state, "#a8aab2")
            status_label = ctk.CTkLabel(api_row, text="✓" if state == "ok" else ("×" if state == "bad" else "□"),
                                        width=28, font=("Segoe UI", 19, "bold"), text_color=status_color)
            status_label.pack(side="left", padx=6)
            s.api_status_widgets[api_key] = status_label
            entry = ctk.CTkEntry(api_row, width=230, show="•", placeholder_text="Paste credential here")
            entry.pack(side="right", padx=(8, 2), pady=4)
            if saved_api_value(api_key, cfg): entry.insert(0, saved_api_value(api_key, cfg))
            key_entries[api_key] = entry
        ctk.CTkLabel(manager, text="Edit a saved key by replacing its field, or clear the field to remove it. Use Show keys to inspect saved values.",
                     text_color="#9aa0b5", font=("Segoe UI", 10), wraplength=520, justify="left").pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(manager, text="No key required today: Apple Search (music previews), Steam Store, Wikipedia, and Wikidata.",
                     text_color="#9aa0b5", font=("Segoe UI", 10), wraplength=520, justify="left").pack(fill="x", padx=12, pady=(8, 12))

        def save_api_keys():
            current = events.load_cfg()
            old_values = {name: saved_api_value(name, current) for name in key_entries}
            new_values = {name: entry.get().strip() for name, entry in key_entries.items()}
            for name, value in new_values.items():
                if name == "igdb_client_secret":
                    protected = local_secrets.protect_text(value)
                    if protected:
                        current["igdb_client_secret_dpapi"] = protected
                        current.pop(name, None)
                    else:
                        current[name] = value
                        current.pop("igdb_client_secret_dpapi", None)
                else:
                    current[name] = value
            statuses = current.setdefault("api_statuses", {})
            for name, value in new_values.items():
                if old_values.get(name, "") != value:
                    state = "not_checked" if value else "not_set"
                    statuses[name] = {"state": state, "message": "Credential changed; refresh to check." if value else "No credential saved."}
                    widget = s.api_status_widgets.get(name)
                    if widget is not None and widget.winfo_exists():
                        widget.configure(text="□", text_color="#a8aab2")
            events.save_cfg(current)

        def update_api_status(api_key, state, message):
            current = events.load_cfg()
            current.setdefault("api_statuses", {})[api_key] = {"state": state, "message": message, "checked_at": int(__import__("time").time())}
            events.save_cfg(current)
            widget = s.api_status_widgets.get(api_key)
            if widget is not None and widget.winfo_exists():
                widget.configure(text="✓" if state == "ok" else ("×" if state == "bad" else "□"),
                                 text_color={"ok": "#45b86b", "bad": "#df4c55"}.get(state, "#a8aab2"))
            if message: s.say(message)
        s.update_api_status = update_api_status

        manager_open = False

        def toggle_key_manager():
            nonlocal manager_open
            manager_open = not manager_open
            if manager_open:
                manager.pack(fill="x", padx=14, pady=(0, 4))
                manager_toggle.configure(text="🔐  API Keys & Integrations  ▴")
            else:
                manager.pack_forget()
                manager_toggle.configure(text="🔐  API Keys & Integrations  ▾")

        manager_toggle = ctk.CTkButton(manager_head, text="🔐  API Keys & Integrations  ▾", height=34,
                                       fg_color=CARD, hover_color=HOVER, command=toggle_key_manager)
        manager_toggle.pack(side="left")
        ctk.CTkButton(manager_head, text="Save keys", width=100, height=34, command=lambda: (save_api_keys(), s.say("API credentials saved on this PC."))).pack(side="left", padx=8)

        def toggle_key_visibility():
            nonlocal show_keys
            show_keys = not show_keys
            for entry in key_entries.values():
                entry.configure(show="" if show_keys else "•")
            visibility_toggle.configure(text="Hide keys" if show_keys else "Show keys")

        visibility_toggle = ctk.CTkButton(manager_head, text="Show keys", width=92, height=34,
                                           fg_color=CARD, hover_color=HOVER, command=toggle_key_visibility)
        visibility_toggle.pack(side="left")

        event_row = ctk.CTkFrame(live, fg_color="transparent"); event_row.pack(fill="x", padx=14, pady=(2, 4))
        ctk.CTkButton(event_row, text="Ticketmaster key", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      command=lambda: webbrowser.open("https://developer.ticketmaster.com/products-and-docs/apis/getting-started/")).pack(side="left")
        ctk.CTkButton(event_row, text="TMDB key", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      command=lambda: webbrowser.open("https://www.themoviedb.org/settings/api")).pack(side="left")
        ctk.CTkButton(event_row, text="Watchmode", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      command=lambda: webbrowser.open("https://api.watchmode.com/")).pack(side="left")
        ctk.CTkButton(event_row, text="IGDB / Twitch", fg_color="transparent", hover_color=HOVER, text_color=GOLD,
                      command=lambda: webbrowser.open("https://dev.twitch.tv/console/apps")).pack(side="left")
        s.status = ctk.CTkLabel(live, text=status or "Credentials stay in this PC's local Spotlight settings. □ not checked   ✓ working   × needs attention",
                                text_color="#9aa0b5", font=("Segoe UI", 11), wraplength=560, justify="center"); s.status.pack(pady=(0, 4))
        ctk.CTkLabel(live, text="This product uses the TMDB API but is not endorsed or certified by TMDB.", text_color="#9aa0b5", font=("Segoe UI", 11)).pack(pady=(0, 10))
        s.sponsor_footer(p)
        enter_button = ctk.CTkButton(dashboard_actions, text="Enter Spotlight  ▶", width=220, height=46, font=("Segoe UI", 17, "bold"), command=s.place_forget)
        enter_button.pack(side="left", padx=8)
        promote_button = ctk.CTkButton(dashboard_actions, text="📣  Promote an event", width=190, height=46, fg_color="#9b6a1c", hover_color="#c48a2a", font=("Segoe UI", 15, "bold"), command=s.app.open_promote)
        promote_button.pack(side="left", padx=8)
        community_button = ctk.CTkButton(dashboard_actions, text="🔄 Community", width=120, height=46, fg_color=CARD, hover_color=HOVER, command=lambda: s.app.sync_community(s.say))
        community_button.pack(side="left", padx=8)
        signout_button = ctk.CTkButton(dashboard_actions, text="Sign out", width=100, height=46, fg_color=CARD, hover_color=HOVER, command=s.sign_out)
        signout_button.pack(side="left", padx=8)
        s.dashboard_action_buttons = [enter_button, promote_button, community_button, signout_button]
        s.refresh_controls = [(area_selector, "normal" if state else "disabled"), (refresh_button, "normal")]
        s.refresh_controls.extend((button, "normal") for button in s.dashboard_action_buttons)
        if s.refreshing: s.set_refreshing(True, jobs=s.refresh_jobs_left)

    def update_dashboard_stats(s):
        """Refresh the visible count cards without clearing or rebuilding the dashboard."""
        if not getattr(s, "stats_value_labels", None): return
        u = s.user or {"city": "", "state": ""}
        city, state = u.get("city") or "", u.get("state") or ""
        st = database.dashboard_stats(city, state, u.get("username") or "__guest__")
        cats = st["cats"]
        values = [st["total"], cats.get("music", 0), cats.get("movies", 0), cats.get("tv", 0), cats.get("games", 0),
                  cats.get("sports", 0), cats.get("festivals", 0), st["events"], st["favorites"], st["near_state"] if state else "-"]
        for label, value in zip(s.stats_value_labels, values):
            try: label.configure(text=str(value))
            except Exception: pass

    def sign_out(s):
        s.user = None; s.show_login()
