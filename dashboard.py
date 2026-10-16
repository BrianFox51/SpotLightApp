"""Spotlight startup gate: Mythic Mask Works banner, sign in / create account / guest, then the Dashboard with live stats.
Branding images are loaded from the project media/ folder, with root/assets fallbacks."""
import os, glob, json, re, shutil, threading, urllib.request, webbrowser, time
from datetime import datetime
from tkinter import filedialog
import customtkinter as ctk
from PIL import Image, ImageOps
import database
import events
import community
import local_secrets
from server_client import ServerAPIError, ServerClient

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
            refreshed_at = int(time.time())
            cfg = events.load_cfg()
            cfg["last_refresh_at"] = refreshed_at
            events.save_cfg(cfg)
            if getattr(s, "last_refresh_label", None) is not None and s.last_refresh_label.winfo_exists():
                s.last_refresh_label.configure(text="Last refreshed: " + datetime.fromtimestamp(refreshed_at).strftime("%b %d, %Y at %I:%M %p"))
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
        ctk.CTkLabel(p, text="Beta version 0.1.1.0", font=("Segoe UI", 13, "bold"),
                     text_color=GOLD).pack(pady=(2, 4))
        tabs = ctk.CTkTabview(p, width=600, height=510, fg_color=PANEL); tabs.pack(pady=8)
        si, su = tabs.add("Sign In"), tabs.add("Create Profile")

        sign_in_form = ctk.CTkScrollableFrame(
            si, fg_color="transparent", width=540, height=470
        )
        sign_in_form.pack(fill="both", expand=True, padx=8, pady=6)

        cfg = events.load_cfg()

        ctk.CTkLabel(
            sign_in_form,
            text="Username or email",
            width=320,
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            text_color="#cfd3e0",
        ).pack(pady=(10, 0))
        u1 = ctk.CTkEntry(
            sign_in_form,
            placeholder_text="Enter username or email",
            width=320,
        )
        u1.pack(pady=(3, 6))

        remembered_user = cfg.get("remembered_username", "")
        if remembered_user:
            u1.insert(0, remembered_user)

        ctk.CTkLabel(
            sign_in_form,
            text="Password",
            width=320,
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            text_color="#cfd3e0",
        ).pack(pady=(4, 0))
        p1 = ctk.CTkEntry(
            sign_in_form,
            placeholder_text="Enter password",
            show="•",
            width=320,
        )
        p1.pack(pady=(3, 6))

        remember = ctk.BooleanVar(value=cfg.get("remember_me", True))
        remembered_password = local_secrets.unprotect_text(
            cfg.get("remembered_password_dpapi", "")
        )
        if remember.get() and remembered_password:
            p1.insert(0, remembered_password)

        ctk.CTkCheckBox(
            sign_in_form,
            text="Remember password on this PC (securely)",
            variable=remember,
        ).pack(anchor="w", padx=70, pady=(2, 2))

        ctk.CTkButton(
            sign_in_form,
            text="Sign In",
            width=320,
            command=lambda: s.do_login(u1.get(), p1.get(), remember.get()),
        ).pack(pady=8)

        s.login_err = ctk.CTkLabel(
            sign_in_form,
            text="",
            text_color="#ff6b6b",
            font=("Segoe UI", 13),
            wraplength=500,
        )
        s.login_err.pack(pady=(0, 4))
        p1.bind("<Return>", lambda e: s.do_login(u1.get(), p1.get(), remember.get()))

        recovery = ctk.CTkFrame(sign_in_form, fg_color="transparent")
        recovery.pack(pady=(0, 4))
        ctk.CTkButton(
            recovery, text="Forgot username?", width=130, height=24,
            fg_color="transparent", hover_color=HOVER,
            text_color="#85899a", state="disabled",
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            recovery, text="Forgot password?", width=130, height=24,
            fg_color="transparent", hover_color=HOVER,
            text_color="#85899a", state="disabled",
        ).pack(side="left", padx=3)
        ctk.CTkLabel(
            sign_in_form,
            text="Account recovery is temporarily unavailable.",
            text_color="#85899a",
            font=("Segoe UI", 11),
        ).pack(pady=(0, 4))

        ctk.CTkButton(
            sign_in_form,
            text="Continue as guest",
            fg_color=CARD,
            hover_color=HOVER,
            command=s.guest,
        ).pack(pady=(8, 4))
        s.sponsor_footer(sign_in_form)

        form = ctk.CTkScrollableFrame(
            su, fg_color="transparent", width=540, height=430
        )
        form.pack(fill="both", expand=True, padx=8, pady=6)
        ctk.CTkLabel(
            form, text="Build your Spotlight profile",
            font=("Segoe UI", 19, "bold"), text_color=GOLD,
        ).pack(anchor="w", padx=12, pady=(4, 2))
        ctk.CTkLabel(
            form,
            text="Required for your account and local event discovery. Your profile stays on this PC.",
            text_color="#9aa0b5", wraplength=500, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 7))

        full_name = ctk.CTkEntry(form, placeholder_text="Full name", width=500)
        full_name.pack(pady=4)
        u2 = ctk.CTkEntry(form, placeholder_text="Username (3+ characters)", width=500)
        u2.pack(pady=4)
        p2 = ctk.CTkEntry(form, placeholder_text="Password (6+ characters)", show="•", width=500)
        p2.pack(pady=4)
        email = ctk.CTkEntry(
            form, placeholder_text="Email address (required for local account recovery)",
            width=500,
        )
        email.pack(pady=4)

        location_row = ctk.CTkFrame(form, fg_color="transparent")
        location_row.pack(fill="x", padx=16, pady=4)
        z2 = ctk.CTkEntry(location_row, placeholder_text="ZIP code", width=240)
        z2.pack(side="left", padx=(0, 8))
        state_entry = ctk.CTkEntry(
            location_row, placeholder_text="State (2-letter code)", width=240
        )
        state_entry.pack(side="left")

        ctk.CTkLabel(
            form, text="Optional community profile details",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=12, pady=(9, 2))
        ctk.CTkLabel(form, text="About you", text_color="#9aa0b5").pack(
            anchor="w", padx=14, pady=(4, 0)
        )
        bio = ctk.CTkTextbox(form, width=500, height=70)
        bio.pack(pady=4)
        interests = ctk.CTkEntry(
            form, placeholder_text="Favorite genres, teams, artists, or games",
            width=500,
        )
        interests.pack(pady=4)
        website = ctk.CTkEntry(
            form, placeholder_text="Website or social link (optional)", width=500
        )
        website.pack(pady=4)

        avatar = {"path": ""}
        avatar_status = ctk.CTkLabel(
            form, text="No profile photo selected", text_color="#9aa0b5"
        )
        avatar_status.pack(anchor="w", padx=14, pady=(5, 0))
        ctk.CTkButton(
            form, text="Choose profile photo", width=180,
            command=lambda: s.choose_avatar(avatar, avatar_status),
        ).pack(anchor="w", padx=12, pady=(3, 6))
        ctk.CTkButton(
            form, text="Create Profile", width=300, height=40,
            command=lambda: s.do_signup(
                u2.get(), p2.get(), z2.get(),
                full_name=full_name.get(),
                state=state_entry.get(),
                email=email.get(),
                bio=bio.get("1.0", "end-1c"),
                interests=interests.get(),
                website=website.get(),
                avatar_path=avatar["path"],
            ),
        ).pack(pady=8)

        s.err = ctk.CTkLabel(
            form, text="", text_color="#ff6b6b",
            font=("Segoe UI", 13), wraplength=500,
        )
        s.err.pack(pady=(0, 6))

    def choose_avatar(s, avatar, status):
        selected = filedialog.askopenfilename(title="Choose a profile photo", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if not selected: return
        try:
            with Image.open(selected) as image: image.verify()
            folder = os.path.join(database.HOME, "profile_images"); os.makedirs(folder, exist_ok=True)
            destination = os.path.join(folder, os.path.basename(selected))
            if os.path.abspath(selected) != os.path.abspath(destination):
                root, ext = os.path.splitext(destination); number = 1
                while os.path.exists(destination):
                    destination = f"{root}_{number}{ext}"; number += 1
                shutil.copy2(selected, destination)
            avatar["path"] = destination; status.configure(text=f"Selected: {os.path.basename(destination)}")
        except Exception as exc:
            status.configure(text=f"Could not load that image: {exc}", text_color="#ff6b6b")

    def recover_account(s, mode):
        dialog = ctk.CTkToplevel(s.app); dialog.title("Recover Spotlight account"); dialog.geometry("440x390" if mode == "password" else "440x270"); dialog.configure(fg_color=BG); dialog.transient(s.app)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL); panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(panel, text="Forgot username?" if mode == "username" else "Reset password on this PC", font=("Segoe UI", 18, "bold")).pack(pady=(14, 5))
        ctk.CTkLabel(panel, text="Enter the email and ZIP code saved to your local profile." if mode == "username" else "This verifies the local profile on this PC; Spotlight does not send recovery email.", text_color="#9aa0b5", wraplength=360, justify="center").pack(pady=(0, 8))
        username = ctk.CTkEntry(panel, placeholder_text="Username", width=340) if mode == "password" else None
        if username: username.pack(pady=5)
        email_box = ctk.CTkEntry(panel, placeholder_text="Account email", width=340); email_box.pack(pady=5)
        zip_box = ctk.CTkEntry(panel, placeholder_text="ZIP code", width=340); zip_box.pack(pady=5)
        new_password = ctk.CTkEntry(panel, placeholder_text="New password (6+ characters)", show="•", width=340) if mode == "password" else None
        if new_password: new_password.pack(pady=5)
        result = ctk.CTkLabel(panel, text="", text_color="#ff6b6b", wraplength=350); result.pack(pady=4)
        def submit():
            if mode == "username":
                recovered = database.username_for_recovery(email_box.get(), zip_box.get())
                result.configure(text=f"Username: {recovered}" if recovered else "No matching local profile was found.", text_color="#77d18b" if recovered else "#ff6b6b")
                return
            password = new_password.get()
            if len(password) < 6: result.configure(text="Password needs at least 6 characters."); return
            if database.reset_password_locally(username.get(), email_box.get(), zip_box.get(), password):
                cfg = events.load_cfg()
                if str(cfg.get("remembered_username", "")).strip().lower() == username.get().strip().lower():
                    cfg.pop("remembered_password_dpapi", None); events.save_cfg(cfg)
                result.configure(text="Password reset. You can sign in now.", text_color="#77d18b")
            else: result.configure(text="No matching local profile was found.")
        ctk.CTkButton(panel, text="Find username" if mode == "username" else "Reset password", width=200, command=submit).pack(pady=7)
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

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
        identifier = u.strip()
        if not identifier or not p:
            s.login_err.configure(text="Enter your username or email and password.")
            return

        local_user = database.verify_user(identifier, p)
        s.login_err.configure(text="Signing in…", text_color="#c9a45c")

        def worker():
            client = None
            tokens = None
            profile = None
            error = None

            try:
                client = ServerClient()
                tokens = client.login(identifier, p)
                profile = client.get_profile(tokens["access_token"])
            except Exception as exc:
                error = exc

            s.app.uiq.put((
                s.finish_login,
                (identifier, p, remember, local_user, client, tokens, profile, error),
            ))

        threading.Thread(target=worker, daemon=True).start()

    def finish_login(s, identifier, password, remember, local_user, client, tokens, profile, error):
        if profile and tokens:
            server_profile = profile.get("profile") or {}
            user = dict(local_user or {})
            user.update(profile)
            user["display_name"] = (
                server_profile.get("full_name")
                or user.get("full_name")
                or profile.get("username", identifier)
            )
            user["city"] = user.get("city", "")
            user["state"] = server_profile.get("state") or user.get("state", "")
            user["zip"] = server_profile.get("zip") or user.get("zip", "")

            s.server_client = client
            s.server_access_token = tokens.get("access_token")
            s.server_refresh_token = tokens.get("refresh_token")
            s.user = user
            s.remember_credentials(identifier, password, remember)
            s.show_dashboard(status="Signed in to the SpotLight server.")
            return

        if local_user:
            s.server_client = None
            s.server_access_token = None
            s.server_refresh_token = None
            s.user = local_user
            s.remember_credentials(identifier, password, remember)

            if error is not None and getattr(error, "status_code", None) is not None:
                status = "Signed in on this PC; the server did not accept this account."
            else:
                status = "Signed in on this PC; the server is unavailable, so online features are off."

            s.show_dashboard(status=status)
            return

        if getattr(error, "status_code", None) == 401:
            message = "Username/email or password is incorrect."
        elif error is not None:
            message = f"Could not sign in: {error}"
        else:
            message = "Sign-in failed. Please try again."

        s.login_err.configure(text=message, text_color="#ff6b6b")

    def do_signup(s, u, p, z, *, full_name="", state="", email="", bio="", interests="", website="", avatar_path=""):
        u, z, state, email, full_name = u.strip(), z.strip(), state.strip().upper(), email.strip(), full_name.strip()
        if not full_name: return s.err.configure(text="Enter your name.")
        if len(u) < 3: return s.err.configure(text="Username needs at least 3 characters.")
        if len(p) < 6: return s.err.configure(text="Password needs at least 6 characters.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): return s.err.configure(text="Enter a valid email address for account recovery.")
        if not (z.isdigit() and len(z) == 5): return s.err.configure(text="Enter a 5-digit US ZIP code.")
        if not re.fullmatch(r"[A-Z]{2}", state): return s.err.configure(text="Enter your 2-letter state code, such as OH.")
        if website and not re.match(r"^https?://", website.strip(), re.I): website = "https://" + website.strip()
        s.err.configure(text="Creating your profile and looking up the ZIP code…", text_color="#c9a45c")
        def worker():
            try:
                city, found_state, lat, lng = lookup_zip(z)
                if found_state and found_state.upper() != state:
                    s.app.uiq.put((s.finish_signup, (u, p, False, f"ZIP code belongs to {found_state}; check your state entry."))); return
                ok, msg = database.create_user(u, p, z, city, found_state or state, lat, lng, full_name=full_name, email=email,
                                               bio=bio, interests=interests, website=website, avatar_path=avatar_path)
                s.app.uiq.put((s.finish_signup, (u, p, ok, msg)))
            except Exception as exc:
                s.app.uiq.put((s.finish_signup, (u, p, False, f"Could not create the profile: {exc}")))
        threading.Thread(target=worker, daemon=True).start()

    def finish_signup(s, username, password, ok, message):
        if not ok:
            try:
                if s.err.winfo_exists(): s.err.configure(text=message, text_color="#ff6b6b")
            except Exception: pass
            return
        s.user = database.verify_user(username, password)
        s.remember_credentials(username, password, True)
        s.show_dashboard()

    def guest(s):
        s.user = {"display_name": "Guest", "city": "", "state": "", "zip": ""}; s.show_dashboard()

    # ---------- dashboard ----------
    def say(s, msg):
        if isinstance(msg, dict):
            msg = msg.get("message") or msg.get("state") or ""
        try: s.status.configure(text=str(msg))
        except Exception: pass

    def show_dashboard(s, status=""):
        s.clear(); p=s.page
        u = s.user or {"display_name": "Guest", "city": "", "state": ""}; city, state = u.get("city") or "", u.get("state") or ""
        st = database.dashboard_stats(city, state, u.get("username") or "__guest__"); c = st["cats"]
        s.logo_label(190)
        if s.user and s.user.get("username"):
            avatar_path = s.user.get("avatar_path") or ""
            avatar_image = None
            try:
                with Image.open(avatar_path) as source:
                    crop = ImageOps.fit(source.convert("RGB"), (112, 112))
                avatar_image = ctk.CTkImage(light_image=crop, dark_image=crop, size=(56, 56)); s.imgs.append(avatar_image)
            except (OSError, ValueError, TypeError):
                avatar_image = None
            avatar_button = ctk.CTkButton(p, text="" if avatar_image else "👤", image=avatar_image, width=64, height=64,
                                           corner_radius=32, fg_color=CARD, hover_color=HOVER, state="disabled")
            avatar_button.place(relx=0.97, y=10, anchor="ne")
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
            s.set_refreshing(True, jobs=6)
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
            start_refresh(s.app.sync_tvmaze, s.say)

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
        last_refresh_at = cfg.get("last_refresh_at")
        last_refresh_text = "Last refreshed: " + (
            datetime.fromtimestamp(last_refresh_at).strftime("%b %d, %Y at %I:%M %p")
            if isinstance(last_refresh_at, (int, float)) and last_refresh_at > 0 else "Not yet refreshed"
        )
        s.last_refresh_label = ctk.CTkLabel(live, text=last_refresh_text,
                                            text_color="#c9a45c", font=("Segoe UI", 11, "bold"))
        s.last_refresh_label.pack(pady=(0, 2))
        s.status = ctk.CTkLabel(live, text="",
                                text_color="#9aa0b5", font=("Segoe UI", 11), wraplength=560, justify="center")
        s.status.pack(pady=(0, 4))
        ctk.CTkLabel(live, text="This product uses the TMDB API but is not endorsed or certified by TMDB.", text_color="#9aa0b5", font=("Segoe UI", 11)).pack(pady=(0, 10))
        s.sponsor_footer(p)
        enter_button = ctk.CTkButton(dashboard_actions, text="Enter Spotlight  ▶", width=220, height=46, font=("Segoe UI", 17, "bold"), command=s.place_forget)
        enter_button.pack(side="left", padx=8)
        promote_button = ctk.CTkButton(dashboard_actions, text="📣  Promote an event", width=190, height=46, fg_color="#9b6a1c", hover_color="#c48a2a", font=("Segoe UI", 15, "bold"), command=s.app.open_promote)
        promote_button.pack(side="left", padx=8)
        community_available = False
        community_button = ctk.CTkButton(dashboard_actions, text="🌐 Community", width=130, height=46, fg_color=CARD, hover_color=HOVER,
                                         state="disabled")
        community_button.pack(side="left", padx=8)
        signout_button = ctk.CTkButton(dashboard_actions, text="Sign out", width=100, height=46, fg_color=CARD, hover_color=HOVER, command=s.sign_out)
        signout_button.pack(side="left", padx=8)
        s.dashboard_action_buttons = [enter_button, promote_button, community_button, signout_button]
        s.refresh_controls = [(area_selector, "normal" if state else "disabled"), (refresh_button, "normal")]
        s.refresh_controls.extend((button, "disabled" if button is community_button and not community_available else "normal") for button in s.dashboard_action_buttons)
        if s.refreshing: s.set_refreshing(True, jobs=s.refresh_jobs_left)
        ctk.CTkLabel(p, text="Community and profile tools are paused until their service and windows are ready.", text_color="#85899a", font=("Segoe UI", 11)).pack(pady=(0, 8))

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

    def show_profile_editor(s):
        if not s.user or not s.user.get("username"):
            s.say("Create a Spotlight profile to edit your account details."); return
        user = database.get_user(s.user["username"])
        dialog = ctk.CTkToplevel(s.app); dialog.title("Your Spotlight profile"); dialog.geometry("600x720"); dialog.minsize(520, 620); dialog.configure(fg_color=BG); dialog.transient(s.app)
        form = ctk.CTkScrollableFrame(dialog, fg_color=PANEL); form.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(form, text="Your profile", font=("Segoe UI", 22, "bold"), text_color=GOLD).pack(anchor="w", padx=12, pady=(8, 4))
        ctk.CTkLabel(form, text="Your details are stored on this PC. Public profile sharing is not enabled in the current local community feed.",
                     text_color="#9aa0b5", wraplength=500, justify="left").pack(anchor="w", padx=12, pady=(0, 10))
        def field(label, placeholder, value=""):
            ctk.CTkLabel(form, text=label, text_color="#cfd3e0").pack(anchor="w", padx=14, pady=(5, 0))
            entry = ctk.CTkEntry(form, placeholder_text=placeholder, width=500); entry.pack(padx=10, pady=3); entry.insert(0, value or ""); return entry
        name = field("Full name", "Your name", user.get("full_name") or user.get("display_name"))
        email = field("Email", "name@example.com", user.get("email"))
        zip_box = field("ZIP code", "5-digit ZIP", user.get("zip"))
        state = field("State", "Two-letter code", user.get("state"))
        ctk.CTkLabel(form, text="About you", text_color="#cfd3e0").pack(anchor="w", padx=14, pady=(7, 0))
        bio = ctk.CTkTextbox(form, width=500, height=80); bio.pack(padx=10, pady=3); bio.insert("1.0", user.get("bio") or "")
        interests = field("Interests", "Genres, teams, artists, games", user.get("interests"))
        website = field("Website or social link", "https://…", user.get("website"))
        avatar = {"path": user.get("avatar_path") or ""}
        avatar_status = ctk.CTkLabel(form, text=os.path.basename(avatar["path"]) if avatar["path"] else "No profile photo selected", text_color="#9aa0b5")
        avatar_status.pack(anchor="w", padx=14, pady=(8, 0))
        ctk.CTkButton(form, text="Choose or replace photo", width=190, command=lambda: s.choose_avatar(avatar, avatar_status)).pack(anchor="w", padx=12, pady=5)
        error = ctk.CTkLabel(form, text="", text_color="#ff6b6b", wraplength=500); error.pack(pady=4)
        def save():
            email_value = email.get().strip(); zip_value = zip_box.get().strip(); state_value = state.get().strip().upper()
            if not name.get().strip(): error.configure(text="Enter your name."); return
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_value): error.configure(text="Enter a valid email address."); return
            if not (zip_value.isdigit() and len(zip_value) == 5): error.configure(text="Enter a 5-digit ZIP code."); return
            if not re.fullmatch(r"[A-Z]{2}", state_value): error.configure(text="Enter a two-letter state code."); return
            values = {"full_name": name.get(), "email": email_value, "zip": zip_value, "state": state_value,
                      "city": user.get("city", ""), "lat": user.get("lat"), "lng": user.get("lng"),
                      "bio": bio.get("1.0", "end-1c"), "interests": interests.get(),
                      "website": website.get(), "avatar_path": avatar["path"]}
            save_button.configure(state="disabled"); error.configure(text="Saving profile and checking ZIP code…", text_color=GOLD)
            def worker():
                try:
                    city, zip_state, lat, lng = lookup_zip(zip_value)
                    if zip_state and zip_state.upper() != state_value:
                        result = (False, f"That ZIP code belongs to {zip_state}.")
                    else:
                        same_zip = zip_value == str(user.get("zip") or "")
                        values.update({"state": zip_state or state_value, "city": city or (values["city"] if same_zip else ""),
                                       "lat": lat if lat is not None else (values["lat"] if same_zip else None),
                                       "lng": lng if lng is not None else (values["lng"] if same_zip else None)})
                        result = database.update_user_profile(user["username"], values)
                except Exception as exc: result = (False, f"Could not save the profile: {exc}")
                s.app.uiq.put((s.finish_profile_update, (dialog, user["username"], error, save_button, *result)))
            threading.Thread(target=worker, daemon=True).start()
        save_button = ctk.CTkButton(form, text="Save profile", width=220, height=40, command=save); save_button.pack(pady=(6, 14))
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_profile_update(s, dialog, username, error, save_button, ok, message):
        if not ok:
            try:
                if error.winfo_exists(): error.configure(text=message, text_color="#ff6b6b")
                if save_button.winfo_exists(): save_button.configure(state="normal")
            except Exception: pass
            return
        s.user = database.get_user(username)
        try:
            if dialog.winfo_exists(): dialog.destroy()
        except Exception: pass
        if s.winfo_ismapped(): s.show_dashboard(message)

    def show_community_hub(s):
        if not community.feed_url():
            s.say("Community is paused until a shared event feed is configured."); return
        dialog = ctk.CTkToplevel(s.app); dialog.title("Spotlight Community"); dialog.geometry("560x500"); dialog.configure(fg_color=BG); dialog.transient(s.app)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL); panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(panel, text="Spotlight Community", font=("Segoe UI", 24, "bold"), text_color=GOLD).pack(pady=(18, 6))
        user = s.user or {}
        ctk.CTkLabel(panel, text=f"Welcome, {user.get('full_name') or user.get('display_name') or 'Guest'}",
                     font=("Segoe UI", 17, "bold")).pack(pady=4)
        if user.get("avatar_path"):
            try:
                with Image.open(user["avatar_path"]) as source: community_avatar = ImageOps.fit(source.convert("RGB"), (112, 112))
                photo = ctk.CTkImage(light_image=community_avatar, dark_image=community_avatar, size=(56, 56)); s.imgs.append(photo)
                ctk.CTkLabel(panel, text="", image=photo).pack(pady=4)
            except (OSError, ValueError): pass
        community_items = []
        for category in ("sports", "festivals"):
            for item in database.load_local_catalog(category):
                try: sources = json.loads(item.get("sources") or "[]")
                except (TypeError, ValueError): sources = []
                if any(str(source).startswith("Community") for source in sources): community_items.append((category, item))
        ctk.CTkLabel(panel, text=f"{len(community_items)} community event{'s' if len(community_items) != 1 else ''} saved on this PC",
                     font=("Segoe UI", 16), text_color="#cfd3e0").pack(pady=(8, 4))
        if not community.feed_url():
            ctk.CTkLabel(panel, text="The shared event feed has not been configured yet. Local event submissions can still be prepared for review.",
                         text_color="#d8bd76", wraplength=460, justify="center").pack(padx=28, pady=4)
        ctk.CTkLabel(panel, text="Spotlight Community brings organizer-submitted events into one discoverable catalog. Listings are reviewed before they are shared through the configured public event feed.",
                     text_color="#9aa0b5", wraplength=460, justify="center").pack(padx=28, pady=12)
        ctk.CTkLabel(panel, text="Profiles and favorites are currently local to this PC. Cross-device member profiles, follows, comments, and messaging need a hosted community service and are not exposed as if they were already live.",
                     text_color="#c9a45c", wraplength=460, justify="center").pack(padx=28, pady=8)
        buttons = ctk.CTkFrame(panel, fg_color="transparent"); buttons.pack(pady=14)
        if community_items:
            ctk.CTkButton(buttons, text="Browse community events", command=lambda: s.browse_community_events(dialog, community_items)).pack(side="left", padx=5)
        ctk.CTkButton(buttons, text="Refresh community listings", command=lambda: (dialog.destroy(), s.app.sync_community(s.say))).pack(side="left", padx=5)
        ctk.CTkButton(buttons, text="Submit an event", fg_color="#9b6a1c", hover_color="#c48a2a",
                      command=lambda: (dialog.destroy(), s.app.open_promote())).pack(side="left", padx=5)
        ctk.CTkButton(panel, text="Close", fg_color=CARD, hover_color=HOVER, command=dialog.destroy).pack(pady=(0, 14))
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def browse_community_events(s, dialog, items):
        dialog.destroy()
        category = items[0][0]
        s.app.gate.place_forget()
        s.app.open_cat(category)
        s.app.items = [item for item_category, item in items if item_category == category]
        s.app.show_genres()
        s.app.pick_genre("All")

    def sign_out(s):
        s.user = None; s.show_login()
