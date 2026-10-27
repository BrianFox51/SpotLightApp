"""Spotlight startup gate: Mythic Mask Works banner, sign in / create account / guest, then the Dashboard with live stats.
Branding images are loaded from the project media/ folder, with root/assets fallbacks."""
import os, glob, json, re, shutil, threading, urllib.request, webbrowser, time
from io import BytesIO
from html import escape, unescape
from html.parser import HTMLParser
from datetime import datetime
from urllib.parse import urlsplit
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk
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


US_STATE_CODES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA",
    "WA", "WV", "WI", "WY",
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


def saved_avatar_path(username):
    """Return the per-device profile photo path for an account, if one was saved."""
    paths = events.load_cfg().get("profile_avatar_paths", {})
    return paths.get(str(username or "").strip().lower(), "") if isinstance(paths, dict) else ""


def save_avatar_path(username, path):
    """Persist a profile photo path locally; image files are never uploaded."""
    cfg = events.load_cfg()
    paths = cfg.setdefault("profile_avatar_paths", {})
    if not isinstance(paths, dict):
        paths = cfg["profile_avatar_paths"] = {}
    key = str(username or "").strip().lower()
    if path:
        paths[key] = path
    else:
        paths.pop(key, None)
    try:
        events.save_cfg(cfg)
        return True
    except OSError:
        return False


class Gate(ctk.CTkFrame):
    def __init__(s, app, base):
        super().__init__(app, fg_color=BG, corner_radius=0)
        s.app, s.user, s.imgs, s.banner, s.logo = app, None, [], find_banner(base), trim_logo(load_logo(base))
        s.refreshing, s.refresh_jobs_left = False, 0
        s.auto_refresh_started = False
        s.auto_refresh_after_id = None
        s.refresh_outcomes = {"success": 0, "failed": 0, "skipped": 0}
        s.refresh_banner = None
        s.refresh_disabled_widgets = []
        s.login_disabled_widgets = []
        s.scroll_block_bindings = []
        s.refresh_card_styles = []
        s.update_in_progress = False
        s.disco_frames, s.disco_frame_index = [], 0
        s.disco_after_id = None
        s.dashboard_logo_canvas = None
        s.tmdb_footer_logo = load_tmdb_logo(base, "tmdb_footer.png")
        s.place(x=0, y=0, relwidth=1, relheight=1); s.show_login()

    def set_refreshing(s, active, jobs=0):
        """Show progress and lock the dashboard until every refresh source returns."""
        s.refreshing = bool(active)
        s.refresh_jobs_left = jobs if active else 0
        if s.refresh_banner is not None and s.refresh_banner.winfo_exists():
            if active:
                try: s.page._parent_canvas.yview_moveto(0)
                except Exception: pass
                s.refresh_banner.pack(fill="x", pady=(0, 5))
            else:
                s.refresh_banner.pack_forget()
        s.update_in_progress = bool(active)
        s.set_dashboard_logo_animation(active)
        s.set_page_controls_disabled(active, "refresh_disabled_widgets")
        s.set_stat_cards_disabled(active)
        s.set_page_scrolling_disabled(active)

    def set_page_controls_disabled(s, disabled, storage_name):
        """Disable interactive controls and gray their surfaces, restoring prior styles later."""
        saved_states = getattr(s, storage_name, [])
        if disabled:
            saved_states = []
            pending = list(s.page.winfo_children()) if getattr(s, "page", None) is not None else []
            interactive = {"CTkButton", "CTkOptionMenu", "CTkComboBox", "CTkSwitch", "CTkSlider",
                           "CTkCheckBox", "CTkRadioButton", "CTkEntry", "CTkTextbox",
                           "CTkSegmentedButton", "CTkTabview", "CTkScrollbar"}
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if widget.__class__.__name__ not in interactive:
                    continue
                try:
                    state = widget.cget("state")
                except Exception:
                    continue
                if state in ("normal", "disabled", "readonly"):
                    styles = {}
                    for option in ("fg_color", "text_color", "hover_color", "button_color",
                                   "button_hover_color", "progress_color"):
                        try: styles[option] = widget.cget(option)
                        except Exception: pass
                    saved_states.append((widget, state, styles))
                    if state != "disabled":
                        try:
                            widget.configure(state="disabled")
                            if widget.__class__.__name__ == "CTkButton":
                                widget.configure(fg_color="#45454f", hover_color="#45454f", text_color="#9a9aa3")
                            else:
                                gray = {name: "#45454f" for name in styles
                                        if name in {"fg_color", "hover_color", "button_color", "button_hover_color", "progress_color"}}
                                if "text_color" in styles: gray["text_color"] = "#9a9aa3"
                                if gray: widget.configure(**gray)
                        except Exception: pass
        else:
            for widget, ready_state, styles in saved_states:
                try:
                    if widget.winfo_exists():
                        widget.configure(**styles)
                        widget.configure(state=ready_state)
                except Exception: pass
            saved_states = []
        setattr(s, storage_name, saved_states)

    def set_stat_cards_disabled(s, disabled):
        if disabled:
            if s.refresh_card_styles: return
            s.refresh_card_styles = []
            for card in getattr(s, "stats_cards", []):
                widgets = [card]
                pending = list(card.winfo_children())
                while pending:
                    widget = pending.pop()
                    pending.extend(widget.winfo_children())
                    widgets.append(widget)
                for widget in widgets:
                    option = "fg_color" if isinstance(widget, ctk.CTkFrame) else "text_color"
                    try:
                        old_value = widget.cget(option)
                        s.refresh_card_styles.append((widget, option, old_value))
                        widget.configure(**{option: "#303039" if option == "fg_color" else "#85858f"})
                    except Exception: pass
        else:
            for widget, option, value in s.refresh_card_styles:
                try:
                    if widget.winfo_exists(): widget.configure(**{option: value})
                except Exception: pass
            s.refresh_card_styles = []

    def set_page_scrolling_disabled(s, disabled):
        if disabled:
            s.scroll_block_bindings = []
            page_widgets = [s.page]
            pending = list(s.page.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                page_widgets.append(widget)
            def block_scroll(_event): return "break"
            for widget in page_widgets:
                for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    try:
                        binding_id = widget.bind(sequence, block_scroll, add="+")
                        if binding_id: s.scroll_block_bindings.append((widget, sequence, binding_id))
                    except Exception: pass
        else:
            for widget, sequence, binding_id in s.scroll_block_bindings:
                try: widget.unbind(sequence, binding_id)
                except Exception: pass
            s.scroll_block_bindings = []

    def load_disco_frames(s):
        if s.disco_frames: return
        path = os.path.join(os.path.dirname(__file__), "media", "refresh_disco.gif")
        try:
            with Image.open(path) as animation:
                for index in range(getattr(animation, "n_frames", 1)):
                    animation.seek(index)
                    frame = animation.convert("RGBA")
                    frame.thumbnail((112, 112), Image.Resampling.LANCZOS)
                    s.disco_frames.append(ImageTk.PhotoImage(frame, master=s))
        except (OSError, ValueError, AttributeError):
            s.disco_frames = []

    def animate_disco_frame(s):
        canvas = s.dashboard_logo_canvas
        if not s.update_in_progress or canvas is None or not canvas.winfo_exists() or not s.disco_frames:
            if canvas is not None and canvas.winfo_exists(): canvas.delete("update_disco")
            s.disco_after_id = None
            return
        canvas.delete("update_disco")
        image = s.disco_frames[s.disco_frame_index]
        s.disco_frame_index = (s.disco_frame_index + 1) % len(s.disco_frames)
        canvas.create_image(canvas.winfo_reqwidth() / 2, canvas.winfo_reqheight() * 0.32,
                            image=image, tags=("update_disco",))
        s.disco_after_id = s.after(70, s.animate_disco_frame)

    def set_dashboard_logo_animation(s, active):
        if active:
            s.load_disco_frames()
            if s.disco_after_id is None: s.animate_disco_frame()
        elif s.disco_after_id is not None:
            try: s.after_cancel(s.disco_after_id)
            except Exception: pass
            s.disco_after_id = None
            if s.dashboard_logo_canvas is not None and s.dashboard_logo_canvas.winfo_exists():
                s.dashboard_logo_canvas.delete("update_disco")

    def refresh_job_finished(s, outcome="success"):
        """Record each source result and summarize the completed refresh accurately."""
        if not s.refreshing:
            return
        if outcome not in s.refresh_outcomes:
            outcome = "failed"
        s.refresh_outcomes[outcome] += 1
        s.refresh_jobs_left = max(0, s.refresh_jobs_left - 1)
        if s.refresh_jobs_left == 0:
            counts = s.refresh_outcomes
            if counts["success"]:
                refreshed_at = int(time.time())
                cfg = events.load_cfg()
                cfg["last_refresh_at"] = refreshed_at
                events.save_cfg(cfg)
                if getattr(s, "last_refresh_label", None) is not None and s.last_refresh_label.winfo_exists():
                    s.last_refresh_label.configure(text="Last refreshed: " + datetime.fromtimestamp(refreshed_at).strftime("%b %d, %Y at %I:%M %p"))
            s.set_refreshing(False)
            s.update_dashboard_stats()
            if counts["failed"] and counts["success"]:
                s.say(f"Refresh finished: {counts['success']} sources updated; {counts['failed']} failed and {counts['skipped']} skipped. Saved cards are still available.")
            elif counts["failed"]:
                s.say(f"Online refresh failed for {counts['failed']} sources; {counts['skipped']} skipped. Saved cards are still available offline.")
            elif counts["success"]:
                s.say(f"Refresh complete: {counts['success']} sources updated; {counts['skipped']} skipped.")
            else:
                s.say("No online sources are configured yet. Saved cards are available; add API keys or ZIP details, then refresh.")

    def clear(s):
        if hasattr(s.app, "hide_favorites_button"):
            s.app.hide_favorites_button()
        for w in s.winfo_children(): w.destroy()
        s.imgs.clear(); s.place(x=0, y=0, relwidth=1, relheight=1); s.lift()
        # Keep the whole gate usable on high-DPI screens with limited vertical space.
        s.page = ctk.CTkScrollableFrame(s, fg_color=BG, corner_radius=0)
        s.page.pack(fill="both", expand=True)

    def logo_label(s, w):
        if s.logo is None:
            ctk.CTkLabel(s.page, text="SPOTLIGHT", font=("Segoe UI", 40, "bold")).pack(pady=(24, 4))
            return
        height = int(w * s.logo.height / s.logo.width)
        logo = s.logo.convert("RGBA").resize((w, height), Image.Resampling.LANCZOS)
        s.dashboard_logo_photo = ImageTk.PhotoImage(logo, master=s)
        canvas = tk.Canvas(s.page, width=w, height=height, bg=BG, highlightthickness=0)
        canvas.pack(pady=(10, 0))
        canvas.create_image(w / 2, height / 2, image=s.dashboard_logo_photo, tags=("brand_logo",))
        s.dashboard_logo_canvas = canvas

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
        s.app.hide_favorites_button()
        s.clear(); s.header(); p=s.page
        ctk.CTkLabel(p, text="Beta version 1.2.4.1", font=("Segoe UI", 13, "bold"),
                     text_color=GOLD).pack(pady=(2, 4))
        tabs = ctk.CTkTabview(p, width=600, height=510, fg_color=PANEL); tabs.pack(pady=8)
        si, su = tabs.add("Sign In"), tabs.add("Create Profile")

        sign_in_form = ctk.CTkScrollableFrame(
            si, fg_color="transparent", width=540, height=470
        )
        sign_in_form.pack(fill="both", expand=True, padx=8, pady=6)

        cfg = events.load_cfg()

        username_row = ctk.CTkFrame(
            sign_in_form, fg_color="transparent", width=320, height=26
        )
        username_row.pack(pady=(10, 0))
        username_row.pack_propagate(False)
        ctk.CTkLabel(
            username_row,
            text="Username or email",
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            text_color="#cfd3e0",
        ).place(relx=0, rely=0.5, anchor="w")
        ctk.CTkButton(
            username_row,
            text="Forgot username?",
            width=112,
            height=24,
            fg_color="transparent",
            hover_color=HOVER,
            text_color="#55aaff",
            font=("Segoe UI", 11),
            command=lambda: s.recover_account("username"),
        ).place(relx=1, rely=0.5, anchor="e")
        u1 = ctk.CTkEntry(
            sign_in_form,
            placeholder_text="Enter username or email",
            width=320,
        )
        u1.pack(pady=(3, 6))

        remembered_user = cfg.get("remembered_username", "")
        if remembered_user:
            u1.insert(0, remembered_user)

        password_row = ctk.CTkFrame(
            sign_in_form, fg_color="transparent", width=320, height=26
        )
        password_row.pack(pady=(4, 0))
        password_row.pack_propagate(False)
        ctk.CTkLabel(
            password_row,
            text="Password",
            anchor="w",
            font=("Segoe UI", 13, "bold"),
            text_color="#cfd3e0",
        ).place(relx=0, rely=0.5, anchor="w")
        ctk.CTkButton(
            password_row,
            text="Forgot password?",
            width=112,
            height=24,
            fg_color="transparent",
            hover_color=HOVER,
            text_color="#55aaff",
            font=("Segoe UI", 11),
            command=lambda: s.recover_account("password"),
        ).place(relx=1, rely=0.5, anchor="e")
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
            text="Remember me on this PC (offline sign-in enabled)",
            variable=remember,
        ).pack(anchor="w", padx=70, pady=(2, 2))

        ctk.CTkButton(
            sign_in_form,
            text="Sign In",
            width=320,
            command=lambda: s.do_login(u1.get(), p1.get(), remember.get()),
        ).pack(pady=8)

        ctk.CTkButton(
            sign_in_form,
            text="Continue as guest",
            fg_color=CARD,
            hover_color=HOVER,
            command=s.guest,
        ).pack(pady=(2, 4))

        ctk.CTkButton(
            sign_in_form,
            text="Server connection settings",
            width=220,
            height=24,
            fg_color="transparent",
            hover_color=HOVER,
            text_color="#9aa0b5",
            font=("Segoe UI", 11),
            command=s.configure_server_connection,
        ).pack(pady=(0, 4))

        login_status_row = ctk.CTkFrame(sign_in_form, fg_color="transparent")
        login_status_row.pack(pady=(0, 4))
        s.login_err = ctk.CTkLabel(
            login_status_row,
            text="",
            text_color="#ff6b6b",
            font=("Segoe UI", 13),
            wraplength=500,
        )
        s.login_err.pack(side="left")
        p1.bind("<Return>", lambda e: s.do_login(u1.get(), p1.get(), remember.get()))

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
            text="Online accounts save profile details to the private Spotlight server. Local profiles stay on this PC.",
            text_color="#9aa0b5", wraplength=500, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 7))

        full_name = ctk.CTkEntry(form, placeholder_text="Full name", width=500)
        full_name.pack(pady=4)
        u2 = ctk.CTkEntry(form, placeholder_text="Username (3+ characters)", width=500)
        u2.pack(pady=4)
        p2 = ctk.CTkEntry(form, placeholder_text="Password (12+ online; 6+ local)", show="•", width=500)
        p2.pack(pady=4)
        email = ctk.CTkEntry(
            form, placeholder_text="Email address",
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
            form, text="No profile photo selected (photos stay on this PC)", text_color="#9aa0b5"
        )
        avatar_status.pack(anchor="w", padx=14, pady=(5, 0))
        ctk.CTkButton(
            form, text="Choose profile photo", width=180,
            command=lambda: s.choose_avatar(avatar, avatar_status),
        ).pack(anchor="w", padx=12, pady=(3, 6))
        def submit_signup(online):
            s.do_signup(
                u2.get(), p2.get(), z2.get(), online=online,
                full_name=full_name.get(), state=state_entry.get(), email=email.get(),
                bio=bio.get("1.0", "end-1c"), interests=interests.get(),
                website=website.get(), avatar_path=avatar["path"],
            )

        signup_buttons = ctk.CTkFrame(form, fg_color="transparent")
        signup_buttons.pack(pady=8)
        s.signup_buttons = [
            ctk.CTkButton(
                signup_buttons, text="Create online account", width=230, height=40,
                command=lambda: submit_signup(True),
            ),
            ctk.CTkButton(
                signup_buttons, text="Create local profile", width=230, height=40,
                fg_color=CARD, hover_color=HOVER,
                command=lambda: submit_signup(False),
            ),
        ]
        for button in s.signup_buttons:
            button.pack(pady=4)

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
            avatar["path"] = destination
            avatar["dirty"] = True
            avatar["remove"] = False
            status.configure(text=f"Selected: {os.path.basename(destination)}")
        except Exception as exc:
            status.configure(text=f"Could not load that image: {exc}", text_color="#ff6b6b")

    def configure_server_connection(s):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("SpotLight server connection")
        dialog.geometry("520x300")
        dialog.minsize(480, 270)
        dialog.configure(fg_color=BG)
        dialog.transient(s.app)
        dialog.grab_set()

        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(
            panel,
            text="Server connection",
            font=("Segoe UI", 19, "bold"),
            text_color=GOLD,
        ).pack(pady=(14, 5))
        ctk.CTkLabel(
            panel,
            text="This address connects online accounts and Community to the SpotLight server. "
                 "Guest and local profiles continue to work without it. Include /api/v1 at the end.",
            text_color="#9aa0b5",
            wraplength=440,
            justify="center",
        ).pack(padx=16, pady=(0, 10))

        address = ctk.CTkEntry(panel, width=430, placeholder_text="http://server-address:8001/api/v1")
        address.pack(pady=5)
        address.insert(0, ServerClient.configured_base_url())
        result = ctk.CTkLabel(panel, text="", text_color="#ff6b6b", wraplength=430)
        result.pack(pady=4)

        def save_address():
            value = address.get().strip().rstrip("/")
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                result.configure(text="Enter a complete address starting with http:// or https://.")
                return
            if not parsed.path.rstrip("/").endswith("/api/v1"):
                result.configure(text="The address must end in /api/v1.")
                return
            cfg = events.load_cfg()
            cfg["server_api_base_url"] = value
            try:
                events.save_cfg(cfg)
            except OSError as exc:
                result.configure(text=f"Could not save the server address: {exc}")
                return
            result.configure(text="Server address saved for this Windows account.", text_color="#77d18b")

        def use_default():
            cfg = events.load_cfg()
            cfg.pop("server_api_base_url", None)
            try:
                events.save_cfg(cfg)
            except OSError as exc:
                result.configure(text=f"Could not restore the default address: {exc}")
                return
            address.delete(0, "end")
            address.insert(0, ServerClient.configured_base_url())
            result.configure(text="Using the app’s default server address.", text_color="#77d18b")

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(pady=(8, 12))
        ctk.CTkButton(buttons, text="Save address", width=150, command=save_address).pack(side="left", padx=5)
        ctk.CTkButton(
            buttons, text="Use app default", width=150, fg_color=CARD, hover_color=HOVER,
            command=use_default,
        ).pack(side="left", padx=5)
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def recover_account(s, mode):
        try:
            client = ServerClient()
        except ServerAPIError:
            return s.recover_local_account(mode)
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Spotlight account recovery")
        dialog.geometry("480x420" if mode == "password" else "480x300")
        dialog.configure(fg_color=BG)
        dialog.transient(s.app)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(panel, text="Forgot username?" if mode == "username" else "Reset your password",
                     font=("Segoe UI", 19, "bold"), text_color=GOLD).pack(pady=(14, 5))
        instruction = ("Enter the email address on your online account. If it matches, we’ll email your username."
                       if mode == "username" else
                       "We’ll email an 8-digit reset code. It expires in 15 minutes and can be used once.")
        ctk.CTkLabel(panel, text=instruction, text_color="#9aa0b5", wraplength=390,
                     justify="center").pack(pady=(0, 10))
        email_box = ctk.CTkEntry(panel, placeholder_text="Account email", width=350)
        email_box.pack(pady=5)
        result = ctk.CTkLabel(panel, text="", text_color="#ff6b6b", wraplength=390)
        result.pack(pady=5)
        reset_frame = ctk.CTkFrame(panel, fg_color="transparent")
        code_box = new_password = reset_button = None
        if mode == "password":
            code_box = ctk.CTkEntry(reset_frame, placeholder_text="8-digit code from email", width=350)
            code_box.pack(pady=4)
            new_password = ctk.CTkEntry(reset_frame, placeholder_text="New password (12+ characters)", show="•", width=350)
            new_password.pack(pady=4)
            reset_button = ctk.CTkButton(reset_frame, text="Reset password", width=190,
                                         command=lambda: s.submit_password_recovery(
                                             client, dialog, email_box, code_box, new_password,
                                             reset_button, result))
            reset_button.pack(pady=5)
        def send_instructions():
            email_value = email_box.get().strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_value):
                result.configure(text="Enter a valid email address.", text_color="#ff6b6b")
                return
            send_button.configure(state="disabled")
            result.configure(text="Sending recovery instructions…", text_color=GOLD)
            def worker():
                try:
                    response = (client.recover_username(email_value) if mode == "username"
                                else client.start_password_recovery(email_value))
                    outcome = (True, response.get("message", "Recovery instructions requested."))
                except Exception as exc:
                    outcome = (False, str(exc))
                s.app.uiq.put((s.finish_recovery_request,
                               (dialog, mode, email_box, reset_frame, send_button, result, *outcome)))
            threading.Thread(target=worker, daemon=True).start()
        send_button = ctk.CTkButton(panel, text="Email my username" if mode == "username" else "Send reset code",
                                    width=210, command=send_instructions)
        send_button.pack(pady=6)
        ctk.CTkButton(panel, text="Recover a local profile on this PC", width=250,
                      fg_color=CARD, hover_color=HOVER,
                      command=lambda: (dialog.destroy(), s.recover_local_account(mode))).pack(pady=(8, 10))
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_recovery_request(s, dialog, mode, email_box, reset_frame, send_button, result, ok, message):
        try:
            if not dialog.winfo_exists(): return
            send_button.configure(state="normal")
            result.configure(text=message, text_color="#77d18b" if ok else "#ff6b6b")
            if ok and mode == "password":
                email_box.configure(state="disabled")
                send_button.configure(text="Code sent · send another", state="normal")
                reset_frame.pack(pady=(0, 4))
        except Exception:
            pass

    def submit_password_recovery(s, client, dialog, email_box, code_box, new_password, button, result):
        email_value, code, password = email_box.get().strip(), code_box.get().strip(), new_password.get()
        if not re.fullmatch(r"\d{8}", code):
            result.configure(text="Enter the 8-digit code from your email.", text_color="#ff6b6b")
            return
        if len(password) < 12:
            result.configure(text="Password needs at least 12 characters.", text_color="#ff6b6b")
            return
        button.configure(state="disabled")
        result.configure(text="Resetting password…", text_color=GOLD)
        def worker():
            try:
                response = client.complete_password_recovery(email_value, code, password)
                outcome = (True, response.get("message", "Password reset. Sign in with your new password."))
            except Exception as exc:
                outcome = (False, str(exc))
            s.app.uiq.put((s.finish_password_recovery, (dialog, button, result, email_value, *outcome)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_password_recovery(s, dialog, button, result, email, ok, message):
        try:
            if not dialog.winfo_exists(): return
            button.configure(state="normal")
            result.configure(text=message, text_color="#77d18b" if ok else "#ff6b6b")
            if ok:
                cfg = events.load_cfg()
                cfg.pop("remembered_password_dpapi", None)
                events.save_cfg(cfg)
                database.forget_cached_server_account(email)
        except Exception:
            pass

    def recover_local_account(s, mode):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Recover local Spotlight profile")
        dialog.geometry("440x390" if mode == "password" else "440x270")
        dialog.configure(fg_color=BG)
        dialog.transient(s.app)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(panel, text="Local profile recovery", font=("Segoe UI", 18, "bold")).pack(pady=(14, 5))
        ctk.CTkLabel(panel, text="This only recovers a profile stored on this PC.", text_color="#9aa0b5",
                     wraplength=360, justify="center").pack(pady=(0, 8))
        username = ctk.CTkEntry(panel, placeholder_text="Username", width=340) if mode == "password" else None
        if username: username.pack(pady=5)
        email_box = ctk.CTkEntry(panel, placeholder_text="Account email", width=340)
        email_box.pack(pady=5)
        zip_box = ctk.CTkEntry(panel, placeholder_text="ZIP code", width=340)
        zip_box.pack(pady=5)
        new_password = ctk.CTkEntry(panel, placeholder_text="New password (6+ characters)", show="•", width=340) if mode == "password" else None
        if new_password: new_password.pack(pady=5)
        result = ctk.CTkLabel(panel, text="", text_color="#ff6b6b", wraplength=350)
        result.pack(pady=4)
        def submit_local():
            if mode == "username":
                recovered = database.username_for_recovery(email_box.get(), zip_box.get())
                result.configure(text=f"Username: {recovered}" if recovered else "No matching local profile was found.",
                                 text_color="#77d18b" if recovered else "#ff6b6b")
                return
            password = new_password.get()
            if len(password) < 6:
                result.configure(text="Password needs at least 6 characters.")
                return
            if database.reset_password_locally(username.get(), email_box.get(), zip_box.get(), password):
                cfg = events.load_cfg()
                if str(cfg.get("remembered_username", "")).strip().lower() == username.get().strip().lower():
                    cfg.pop("remembered_password_dpapi", None)
                    events.save_cfg(cfg)
                result.configure(text="Password reset. You can sign in now.", text_color="#77d18b")
            else:
                result.configure(text="No matching local profile was found.")
        ctk.CTkButton(panel, text="Find username" if mode == "username" else "Reset password",
                      width=200, command=submit_local).pack(pady=7)
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
        cached_server_user = database.verify_cached_server_account(identifier, p) if remember else None
        if not remember:
            database.forget_cached_server_account(identifier)
        s.login_err.configure(text="Please wait while the system updates", text_color="#c9a45c")
        s.login_wait_started = time.monotonic()
        s.update_in_progress = True
        s.set_dashboard_logo_animation(True)
        s.set_page_scrolling_disabled(True)
        s.set_page_controls_disabled(True, "login_disabled_widgets")
        s.login_err.update_idletasks()

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
                (identifier, p, remember, local_user, cached_server_user, client, tokens, profile, error),
            ))

        threading.Thread(target=worker, daemon=True).start()

    def finish_login(s, identifier, password, remember, local_user, cached_server_user, client, tokens, profile, error):
        wait_started = getattr(s, "login_wait_started", None)
        if wait_started is not None:
            remaining_ms = max(0, 700 - int((time.monotonic() - wait_started) * 1000))
            if remaining_ms:
                s.after(remaining_ms, lambda: s.finish_login(
                    identifier, password, remember, local_user, cached_server_user, client, tokens, profile, error
                ))
                return
            s.login_wait_started = None
            s.update_in_progress = False
            s.set_dashboard_logo_animation(False)
            s.set_page_scrolling_disabled(False)
            s.set_page_controls_disabled(False, "login_disabled_widgets")
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
            user["full_name"] = server_profile.get("full_name") or user.get("full_name", "")
            user["bio"] = server_profile.get("bio") or ""
            user["interests"] = server_profile.get("interests") or ""
            user["website"] = server_profile.get("site") or ""
            user["avatar_path"] = (local_user or {}).get("avatar_path") or saved_avatar_path(profile.get("username"))

            s.server_client = client
            s.server_access_token = tokens.get("access_token")
            s.server_refresh_token = tokens.get("refresh_token")
            s.user = user
            try:
                if remember:
                    database.cache_server_account(
                        profile.get("username", identifier),
                        profile.get("email", ""),
                        password,
                        user,
                    )
                else:
                    database.forget_cached_server_account(identifier)
            except Exception:
                pass
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

        # Cached online accounts work only when the server cannot be reached.
        # A server rejection (such as a wrong or reset password) must not be
        # bypassed by an older local verifier.
        if cached_server_user and error is not None and getattr(error, "status_code", None) is None:
            s.server_client = None
            s.server_access_token = None
            s.server_refresh_token = None
            s.user = cached_server_user
            s.remember_credentials(identifier, password, remember)
            s.show_dashboard(
                status="Signed in offline on this PC. Online features are unavailable; saved cards remain available."
            )
            return

        if getattr(error, "status_code", None) == 401:
            message = "Username/email or password is incorrect."
        elif error is not None:
            message = f"Could not sign in: {error}"
        else:
            message = "Sign-in failed. Please try again."

        s.login_err.configure(text=message, text_color="#ff6b6b")

    def do_signup(s, u, p, z, *, online=False, full_name="", state="", email="", bio="", interests="", website="", avatar_path=""):
        u, z, state, email, full_name = u.strip(), z.strip(), state.strip().upper(), email.strip(), full_name.strip()
        if not full_name: return s.err.configure(text="Enter your name.")
        if len(u) < 3: return s.err.configure(text="Username needs at least 3 characters.")
        minimum_password_length = 12 if online else 6
        if len(p) < minimum_password_length:
            return s.err.configure(text=f"Password needs at least {minimum_password_length} characters.")
        if online and not re.fullmatch(r"[A-Za-z0-9_]{3,40}", u):
            return s.err.configure(text="Online usernames must be 3–40 letters, numbers, or underscores.")
        if online and len(full_name) > 120:
            return s.err.configure(text="Your name must be 120 characters or fewer.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): return s.err.configure(text="Enter a valid email address.")
        if not (z.isdigit() and len(z) == 5): return s.err.configure(text="Enter a 5-digit US ZIP code.")
        if not re.fullmatch(r"[A-Z]{2}", state): return s.err.configure(text="Enter your 2-letter state code, such as OH.")
        if website and not re.match(r"^https?://", website.strip(), re.I): website = "https://" + website.strip()
        if online and len(bio) > 2000:
            return s.err.configure(text="About you must be 2,000 characters or fewer.")
        if online and len(interests) > 4000:
            return s.err.configure(text="Interests must be 4,000 characters or fewer.")
        if online and len(website) > 255:
            return s.err.configure(text="Your website or social link must be 255 characters or fewer.")
        for button in getattr(s, "signup_buttons", []):
            button.configure(state="disabled")
        s.err.configure(text="Creating your online account and profile…" if online else "Creating your local profile and looking up the ZIP code…", text_color="#c9a45c")
        def worker():
            try:
                city, found_state, lat, lng = lookup_zip(z)
                if found_state and found_state.upper() != state:
                    if online:
                        s.app.uiq.put((s.finish_server_signup, (u, p, None, None, None, city, avatar_path,
                            f"ZIP code belongs to {found_state}; check your state entry.")))
                    else:
                        s.app.uiq.put((s.finish_signup, (u, p, False, f"ZIP code belongs to {found_state}; check your state entry.")))
                    return
                state_value = found_state or state
                if online:
                    client = ServerClient()
                    account_created = False
                    try:
                        client.register(email, u, p)
                        account_created = True
                        tokens = client.login(u, p)
                        access_token = tokens["access_token"]
                        client.update_profile(access_token, {
                            "full_name": full_name,
                            "state": state_value,
                            "zip": z,
                            "bio": bio,
                            "interests": interests,
                            "site": website,
                        })
                        if avatar_path:
                            client.upload_profile_avatar(access_token, avatar_path)
                        profile = client.get_profile(access_token)
                        s.app.uiq.put((s.finish_server_signup, (u, p, client, tokens, profile, city, avatar_path, None)))
                    except Exception as exc:
                        s.app.uiq.put((s.finish_server_signup, (u, p, client, None, None, city, avatar_path,
                            f"Online account was created, but setup did not finish: {exc}. Please sign in to continue." if account_created else f"Could not create the online account: {exc}")))
                    return
                ok, msg = database.create_user(u, p, z, city, state_value, lat, lng, full_name=full_name, email=email,
                                               bio=bio, interests=interests, website=website, avatar_path=avatar_path)
                s.app.uiq.put((s.finish_signup, (u, p, ok, msg)))
            except Exception as exc:
                if online:
                    s.app.uiq.put((s.finish_server_signup, (u, p, None, None, None, "", avatar_path, f"Could not create the online account: {exc}")))
                else:
                    s.app.uiq.put((s.finish_signup, (u, p, False, f"Could not create the profile: {exc}")))
        threading.Thread(target=worker, daemon=True).start()

    def finish_signup(s, username, password, ok, message):
        if not ok:
            try:
                if s.err.winfo_exists(): s.err.configure(text=message, text_color="#ff6b6b")
                for button in getattr(s, "signup_buttons", []):
                    if button.winfo_exists(): button.configure(state="normal")
            except Exception: pass
            return
        s.user = database.verify_user(username, password)
        s.remember_credentials(username, password, True)
        s.show_dashboard()

    def finish_server_signup(s, username, password, client, tokens, profile, city, avatar_path, error):
        if error or not tokens or not profile:
            try:
                if s.err.winfo_exists(): s.err.configure(text=error or "Online account setup did not finish.", text_color="#ff6b6b")
                for button in getattr(s, "signup_buttons", []):
                    if button.winfo_exists(): button.configure(state="normal")
            except Exception: pass
            return
        server_profile = profile.get("profile") or {}
        save_avatar_path(username, avatar_path)
        s.server_client = client
        s.server_access_token = tokens.get("access_token")
        s.server_refresh_token = tokens.get("refresh_token")
        s.user = {
            **profile,
            "display_name": server_profile.get("full_name") or profile.get("username", username),
            "full_name": server_profile.get("full_name") or "",
            "city": city,
            "state": server_profile.get("state") or "",
            "zip": server_profile.get("zip") or "",
            "bio": server_profile.get("bio") or "",
            "interests": server_profile.get("interests") or "",
            "website": server_profile.get("site") or "",
            "avatar_path": avatar_path or "",
        }
        try:
            database.cache_server_account(
                profile.get("username", username),
                profile.get("email", ""),
                password,
                s.user,
            )
        except Exception:
            pass
        s.remember_credentials(username, password, True)
        s.show_dashboard(status="Online Spotlight account created and signed in.")

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
        s.app._prune_expired_event_cache()
        cfg = events.load_cfg()
        preferences = cfg.get("search_state_preferences", {})
        account_key = u.get("username") or "__guest__"
        selected_state = (preferences.get(account_key) or state or "").upper() if u.get("username") else ""
        s.app.search_area_state = selected_state or None
        if selected_state:
            s.app.search_area_scope = f"state:{selected_state}"
        elif cfg.get("guest_ip_location", {}).get("latitude") is not None and cfg.get("guest_ip_location", {}).get("longitude") is not None:
            guest_location = cfg["guest_ip_location"]
            s.app.search_area_scope = f"local:{float(guest_location['latitude']):.2f},{float(guest_location['longitude']):.2f}"
        else:
            s.app.search_area_scope = "local:unknown"
        is_guest = not bool(u.get("username"))
        st = database.dashboard_stats(city, selected_state or state, account_key, guest_only=is_guest); c = st["cats"]
        for category in ("music", "sports", "festivals"):
            c[category] = len(s.app.load_catalog_items(category))
        st["total"] = sum(c.get(category, 0) for category in ("music", "movies", "tv", "games", "sports", "festivals"))
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
                                           corner_radius=32, fg_color=CARD, hover_color=HOVER,
                                           command=s.show_profile_editor)
            avatar_button.place(relx=0.97, y=10, anchor="ne")
        ctk.CTkLabel(p, text=f"Welcome, {u.get('display_name', 'Guest')}", font=("Segoe UI", 20), text_color=GOLD).pack()
        where = ", ".join(x for x in (city, state) if x)
        if not u.get("username"):
            loc = cfg.get("guest_ip_location", {})
            approx = ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
            where = f"Local · approximate area near {approx}" if approx else "Local · approximate area"
        elif not where:
            where = "Add your location in your profile to see what's near you"
        s.location_label = ctk.CTkLabel(p, text="📍  " + where, text_color="#9aa0b5", font=("Segoe UI", 14))
        s.location_label.pack(pady=(2, 22))
        s.top_status_area = ctk.CTkFrame(p, fg_color="transparent")
        s.top_status_area.pack(pady=(0, 10))
        s.refresh_banner = ctk.CTkFrame(s.top_status_area, fg_color="#42351d", corner_radius=10)
        ctk.CTkLabel(s.refresh_banner, text="Please wait while the system updates",
                     fg_color="transparent", text_color="#f0cf78",
                     font=("Segoe UI", 14, "bold"), padx=16, pady=11).pack()
        if s.refreshing:
            s.refresh_banner.pack(fill="x", pady=(0, 5))
        last_refresh_at = cfg.get("last_refresh_at")
        last_refresh_text = "Last refreshed: " + (
            datetime.fromtimestamp(last_refresh_at).strftime("%b %d, %Y at %I:%M %p")
            if isinstance(last_refresh_at, (int, float)) and last_refresh_at > 0 else "Not yet refreshed"
        )
        s.last_refresh_label = ctk.CTkLabel(s.top_status_area, text=last_refresh_text,
                                            text_color="#c9a45c", font=("Segoe UI", 11, "bold"))
        s.last_refresh_label.pack(pady=(0, 2))
        s.status = ctk.CTkLabel(s.top_status_area, text="",
                                text_color="#9aa0b5", font=("Segoe UI", 11), wraplength=560, justify="center")
        s.status.pack(pady=(0, 4))
        dashboard_actions = ctk.CTkFrame(p, fg_color="transparent"); dashboard_actions.pack(pady=(0, 18))
        cards = [("Titles found", st["total"]), ("🎵 Music", c.get("music", 0)), ("🎬 Movies", c.get("movies", 0)), ("📺 TV", c.get("tv", 0)),
                 ("🎮 Games", c.get("games", 0)), ("🏆 Sports", c.get("sports", 0)), ("🎪 Festivals", c.get("festivals", 0)), ("📍 Local events saved", st["events"]),
                 ("⭐ Favorites", st["favorites"]),
                 (f"Items with saved events in {selected_state}" if selected_state else "Saved event titles", st["near_state"] if selected_state else "")]
        grid = ctk.CTkFrame(p, fg_color="transparent"); grid.pack()
        s.stats_value_labels = []
        s.stats_caption_labels = []
        s.stats_cards = []
        for i, (label, val) in enumerate(cards):
            f = ctk.CTkFrame(grid, width=200, height=110, fg_color=CARD, corner_radius=16); f.grid(row=i // 5, column=i % 5, padx=8, pady=8); f.pack_propagate(False)
            s.stats_cards.append(f)
            value_label = ctk.CTkLabel(f, text=str(val), font=("Segoe UI", 34, "bold"), text_color=GOLD); value_label.pack(pady=(16, 0))
            s.stats_value_labels.append(value_label)
            caption = ctk.CTkLabel(f, text=label, font=("Segoe UI", 13), text_color="#9aa0b5")
            caption.pack()
            s.stats_caption_labels.append(caption)
            quick_category = {1: "music", 2: "movies", 3: "tv", 4: "games", 5: "sports", 6: "festivals"}.get(i)
            if quick_category:
                s.bind_stat_card(f, lambda category=quick_category: s.open_dashboard_category(category))
            elif i == 8:
                s.bind_stat_card(f, s.open_dashboard_favorites)
        live = ctk.CTkFrame(p, fg_color=CARD, corner_radius=14); live.pack(pady=(6, 0))
        def saved_api_value(name, source):
            if name == "igdb_client_secret":
                return local_secrets.unprotect_text(source.get("igdb_client_secret_dpapi", "")) or source.get(name, "")
            return source.get(name, "")
        ctk.CTkLabel(live, text="🌐  Spotlight data sources", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        area_row = ctk.CTkFrame(live, fg_color="transparent"); area_row.pack(anchor="w", padx=14, pady=(6, 2))
        ctk.CTkLabel(area_row, text="Search area", text_color="#9aa0b5").pack(side="left", padx=(0, 8))
        state_choice = f"{selected_state} (Select a different state)" if selected_state else "Local"
        area_choices = [f"{code} (Select a different state)" for code in US_STATE_CODES]
        area = ctk.StringVar(value=state_choice)
        is_member = bool(u.get("username"))
        area_selector = ctk.CTkOptionMenu(area_row, values=area_choices, variable=area, width=245)
        def set_area(choice):
            nonlocal selected_state
            if not is_member:
                area.set("Local")
                messagebox.showinfo("Spotlight", "Create a profile to enjoy these features.", parent=s.winfo_toplevel())
                return
            selected_state = choice[:2].upper()
            area.set(f"{selected_state} (Select a different state)")
            cfg_now = events.load_cfg()
            cfg_now.setdefault("search_state_preferences", {})[account_key] = selected_state
            events.save_cfg(cfg_now)
            s.app.search_area_state = selected_state
            s.app.search_area_scope = f"state:{selected_state}"
            s.update_dashboard_stats()
            s.say(f"Search area set to {selected_state}. Press Refresh to load events there; cached cards remain saved.")
        area_selector.configure(command=set_area)
        area_selector.pack(side="left")
        if not is_member:
            ctk.CTkLabel(live, text="Local uses an approximate IP location; the approximate area is cached on this PC.",
                         text_color="#85899a", font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(0, 4))
        s.app.search_area_state = selected_state or None
        s.app.search_area_scope = f"state:{selected_state}" if selected_state else "local:unknown"
        clear_cache_button = None
        def refresh_all(save_keys=True):
            if s.refreshing: return
            if save_keys:
                save_api_keys()
            s.refresh_outcomes = {"success": 0, "failed": 0, "skipped": 0}
            selected_state = s.app.search_area_state
            s.set_refreshing(True, jobs=6)
            current = events.load_cfg()
            report = lambda key, state, message: s.app.uiq.put((s.update_api_status, (key, state, message)))
            done = lambda outcome="success": s.app.uiq.put((s.refresh_job_finished, (outcome,)))
            def start_refresh(job, *args):
                try: job(*args, done)
                except Exception as exc:
                    s.say(f"A refresh source could not start: {exc}")
                    done("failed")
            start_refresh(s.app.sync_tmdb, s.say, current.get("tmdb_key", ""), report)
            start_refresh(s.app.sync_events, s.say, selected_state, report)
            start_refresh(s.app.sync_ohio_schedules, s.say, selected_state or "")
            start_refresh(s.app.sync_watchmode, s.say, current.get("watchmode_key", ""), report)
            start_refresh(s.app.sync_igdb, s.say, current.get("igdb_client_id", ""), saved_api_value("igdb_client_secret", current), report)
            start_refresh(s.app.sync_tvmaze, s.say)

        refresh_button = ctk.CTkButton(area_row, text="🔄  Refresh", width=125, command=refresh_all)
        refresh_button.pack(side="left", padx=(10, 0))
        if str((s.user or {}).get("role", "")).strip().lower() == "admin" and getattr(s, "server_access_token", None):
            clear_cache_button = ctk.CTkButton(
                area_row, text="Clear card cache", width=132,
                fg_color="#6b2b35", hover_color="#8a3946",
                command=lambda: s.clear_catalog_cache(),
            )
            clear_cache_button.pack(side="left", padx=(8, 0))

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
        ctk.CTkLabel(live, text="This product uses the TMDB API but is not endorsed or certified by TMDB.", text_color="#9aa0b5", font=("Segoe UI", 11)).pack(pady=(0, 10))
        s.sponsor_footer(p)
        enter_button = ctk.CTkButton(dashboard_actions, text="Enter Spotlight  ▶", width=220, height=46, font=("Segoe UI", 17, "bold"), command=s.enter_spotlight)
        enter_button.pack(side="left", padx=8)
        promote_button = ctk.CTkButton(dashboard_actions, text="📣  Promote an event", width=190, height=46, fg_color="#9b6a1c", hover_color="#c48a2a", font=("Segoe UI", 15, "bold"), command=s.app.open_promote)
        promote_button.pack(side="left", padx=8)
        community_button = ctk.CTkButton(dashboard_actions, text="🌐 Community", width=130, height=46, fg_color=CARD, hover_color=HOVER,
                                         command=s.show_community_hub)
        community_button.pack(side="left", padx=8)
        signout_button = ctk.CTkButton(dashboard_actions, text="Sign out", width=100, height=46, fg_color=CARD, hover_color=HOVER, command=s.sign_out)
        signout_button.pack(side="left", padx=8)
        s.dashboard_action_buttons = [enter_button, promote_button, community_button, signout_button]
        if s.refreshing: s.set_refreshing(True, jobs=s.refresh_jobs_left)
        ctk.CTkLabel(p, text="Spotlight Community is a member discussion board.", text_color="#85899a", font=("Segoe UI", 11)).pack(pady=(0, 8))
        if not s.auto_refresh_started:
            s.auto_refresh_started = True
            def start_auto_refresh():
                s.auto_refresh_after_id = None
                if s.user is not None and s.winfo_exists():
                    refresh_all(save_keys=False)
            s.auto_refresh_after_id = s.after(300, start_auto_refresh)

    def refresh_guest_location(s, location):
        """Update the guest's approximate location label after background IP lookup."""
        if not s.user or s.user.get("username"):
            return
        cfg = events.load_cfg()
        cfg["guest_ip_location"] = location
        events.save_cfg(cfg)
        approx = ", ".join(x for x in (location.get("city"), location.get("region")) if x)
        try:
            s.app.search_area_scope = f"local:{float(location['latitude']):.2f},{float(location['longitude']):.2f}"
        except (KeyError, TypeError, ValueError):
            pass
        text = f"📍  Local · approximate area near {approx}" if approx else "📍  Local · approximate area"
        try:
            if getattr(s, "location_label", None) and s.location_label.winfo_exists():
                s.location_label.configure(text=text)
        except Exception:
            pass
        try:
            if not s.winfo_ismapped() and getattr(s.app, "cat", None):
                s.app.items = s.app.load_catalog_items(s.app.cat)
                if s.app.genre is None:
                    s.app.show_genres()
        except Exception:
            pass

    def update_dashboard_stats(s):
        """Refresh the visible count cards without clearing or rebuilding the dashboard."""
        if not getattr(s, "stats_value_labels", None): return
        u = s.user or {"city": "", "state": ""}
        city, state = u.get("city") or "", u.get("state") or ""
        selected_state = getattr(s.app, "search_area_state", None) or state
        st = database.dashboard_stats(city, selected_state, u.get("username") or "__guest__",
                                      guest_only=not bool(u.get("username")))
        cats = st["cats"]
        for category in ("music", "sports", "festivals"):
            cats[category] = len(s.app.load_catalog_items(category))
        st["total"] = sum(cats.get(category, 0) for category in ("music", "movies", "tv", "games", "sports", "festivals"))
        values = [st["total"], cats.get("music", 0), cats.get("movies", 0), cats.get("tv", 0), cats.get("games", 0),
                  cats.get("sports", 0), cats.get("festivals", 0), st["events"], st["favorites"], st["near_state"] if selected_state else ""]
        captions = ["Titles found", "🎵 Music", "🎬 Movies", "📺 TV", "🎮 Games", "🏆 Sports", "🎪 Festivals", "📍 Local events saved", "⭐ Favorites",
                    f"Items with saved events in {selected_state}" if selected_state else "Saved event titles"]
        for label, value in zip(s.stats_value_labels, values):
            try: label.configure(text=str(value))
            except Exception: pass
        for label, caption in zip(getattr(s, "stats_caption_labels", []), captions):
            try: label.configure(text=caption)
            except Exception: pass

    def clear_catalog_cache(s):
        """Allow a server-authenticated administrator to clear safe local card cache rows."""
        user = s.user or {}
        if str(user.get("role", "")).strip().lower() != "admin" or not getattr(s, "server_access_token", None):
            s.say("Only a signed-in server administrator can clear the card cache.")
            return
        if s.refreshing:
            s.say("Wait for the current refresh to finish before clearing the card cache.")
            return
        confirmed = messagebox.askyesno(
            "Clear cached cards",
            "This removes cached catalog cards and their linked event and credit rows from this PC. "
            "Cards with a favorite or personal note are kept. User accounts, favorites, API keys, "
            "metadata, and image files are not changed. Continue?",
            parent=s.app,
        )
        if not confirmed:
            return
        removed = database.clear_unfavorited_catalog_cache()
        cfg = events.load_cfg()
        cfg["last_refresh_at"] = 0
        cfg.pop("tmdb_server_cursor", None)
        events.save_cfg(cfg)
        s.update_dashboard_stats()
        s.say(
            f"Cleared {removed['cards']} cached cards and {removed['events']} event rows; "
            f"kept {removed['kept']} cards with favorites or notes. Press Refresh or sign out and "
            f"back in to repopulate from available sources."
        )

    def bind_stat_card(s, card, action):
        """Make a dashboard stat tile a clear, hoverable shortcut."""
        def activate(_event=None):
            if s.refreshing: return "break"
            action()
            return "break"
        def hover(_event=None):
            if s.refreshing: return
            try: card.configure(fg_color=HOVER)
            except Exception: pass
        def restore(_event=None):
            if s.refreshing: return
            try: card.configure(fg_color=CARD)
            except Exception: pass
        pending = [card]
        while pending:
            widget = pending.pop()
            widget.bind("<Button-1>", activate, add="+")
            widget.bind("<Enter>", hover, add="+")
            widget.bind("<Leave>", restore, add="+")
            for child in widget.winfo_children(): pending.append(child)

    def open_dashboard_category(s, category):
        s.app.pinned = True
        s.app.open_cat(category)
        s.place_forget()

    def enter_spotlight(s):
        s.place_forget()
        s.app.show_favorites_button()

    def open_dashboard_favorites(s):
        user = s.user or {}
        if not user.get("username"):
            messagebox.showinfo("Spotlight", "Please register to enable this feature", parent=s.winfo_toplevel())
            return
        s.app.open_favorites()

    def show_profile_editor(s):
        if not s.user or not s.user.get("username"):
            s.say("Create a Spotlight profile to edit your account details."); return
        username = s.user["username"]
        local_user = database.get_user(username)
        online = bool(getattr(s, "server_client", None) and getattr(s, "server_access_token", None))
        user = dict(local_user or s.user)
        server_profile = s.user.get("profile") or {}
        if online:
            user.update({
                "full_name": server_profile.get("full_name") or s.user.get("full_name") or s.user.get("display_name", ""),
                "email": s.user.get("email", ""),
                "zip": server_profile.get("zip") or s.user.get("zip", ""),
                "state": server_profile.get("state") or s.user.get("state", ""),
                "bio": server_profile.get("bio") or s.user.get("bio", ""),
                "interests": server_profile.get("interests") or s.user.get("interests", ""),
                "website": server_profile.get("site") or s.user.get("website", ""),
                "avatar_path": s.user.get("avatar_path") or saved_avatar_path(username),
            })
        dialog = ctk.CTkToplevel(s.app); dialog.title("Your Spotlight profile"); dialog.geometry("600x720"); dialog.minsize(520, 620); dialog.resizable(True, True); dialog.configure(fg_color=BG)
        form = ctk.CTkScrollableFrame(dialog, fg_color=PANEL); form.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(form, text="Your profile", font=("Segoe UI", 22, "bold"), text_color=GOLD).pack(anchor="w", padx=12, pady=(8, 4))
        profile_note = ("Your name, role, and join date are visible to members. Email and ZIP stay private. Choose which other profile details to share."
                        if online else "Your details are stored on this PC. Public profile sharing is not enabled in the current local community feed.")
        ctk.CTkLabel(form, text=profile_note,
                     text_color="#9aa0b5", wraplength=500, justify="left").pack(anchor="w", padx=12, pady=(0, 10))
        visibility_vars = {}
        if online:
            ctk.CTkLabel(form, text="Public profile sharing", text_color=GOLD,
                         font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=(2, 2))
            for key, label in (("show_avatar", "Show my profile photo"), ("show_state", "Show my state"),
                               ("show_bio", "Show my About you text"), ("show_interests", "Show my interests"),
                               ("show_site", "Show my website or social link")):
                variable = ctk.BooleanVar(value=bool(server_profile.get(key, False)))
                visibility_vars[key] = variable
                ctk.CTkCheckBox(form, text=label, variable=variable, text_color="#cfd3e0").pack(anchor="w", padx=16, pady=2)
        def field(label, placeholder, value=""):
            ctk.CTkLabel(form, text=label, text_color="#cfd3e0").pack(anchor="w", padx=14, pady=(5, 0))
            entry = ctk.CTkEntry(form, placeholder_text=placeholder, width=500); entry.pack(padx=10, pady=3); entry.insert(0, value or ""); return entry
        name = field("Full name", "Your name", user.get("full_name") or user.get("display_name"))
        email = field("Email", "name@example.com", user.get("email"))
        if online:
            email.configure(state="disabled")
        zip_box = field("ZIP code", "5-digit ZIP", user.get("zip"))
        state = field("State", "Two-letter code", user.get("state"))
        ctk.CTkLabel(form, text="About you", text_color="#cfd3e0").pack(anchor="w", padx=14, pady=(7, 0))
        bio = ctk.CTkTextbox(form, width=500, height=80); bio.pack(padx=10, pady=3); bio.insert("1.0", user.get("bio") or "")
        interests = field("Interests", "Genres, teams, artists, games", user.get("interests"))
        website = field("Website or social link", "https://…", user.get("website"))
        avatar = {"path": user.get("avatar_path") or "", "dirty": False, "remove": False}
        avatar_status = ctk.CTkLabel(form, text=("Server profile photo saved" if online and server_profile.get("avatar_ref") else os.path.basename(avatar["path"]) if avatar["path"] else "No profile photo selected"), text_color="#9aa0b5")
        avatar_status.pack(anchor="w", padx=14, pady=(8, 0))
        ctk.CTkButton(form, text="Choose or replace photo", width=190, command=lambda: s.choose_avatar(avatar, avatar_status)).pack(anchor="w", padx=12, pady=5)
        if online:
            def remove_server_avatar():
                avatar.update({"path": "", "dirty": True, "remove": True})
                avatar_status.configure(text="Server photo will be removed when you save.")
            ctk.CTkButton(form, text="Remove server photo", width=190, fg_color=CARD, hover_color=HOVER,
                          command=remove_server_avatar).pack(anchor="w", padx=12, pady=(0, 8))
            ctk.CTkLabel(form, text="Photos are optimized and stored on the SpotLight server (up to 100 KB).",
                         text_color="#9aa0b5", wraplength=500, justify="left").pack(anchor="w", padx=14, pady=(0, 5))
        error = ctk.CTkLabel(form, text="", text_color="#ff6b6b", wraplength=500); error.pack(pady=4)
        def save():
            email_value = email.get().strip(); zip_value = zip_box.get().strip(); state_value = state.get().strip().upper()
            if not name.get().strip(): error.configure(text="Enter your name."); return
            if not online and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_value): error.configure(text="Enter a valid email address."); return
            if not (zip_value.isdigit() and len(zip_value) == 5): error.configure(text="Enter a 5-digit ZIP code."); return
            if not re.fullmatch(r"[A-Z]{2}", state_value): error.configure(text="Enter a two-letter state code."); return
            if online and len(name.get().strip()) > 120: error.configure(text="Your name must be 120 characters or fewer."); return
            if online and len(bio.get("1.0", "end-1c")) > 2000: error.configure(text="About you must be 2,000 characters or fewer."); return
            if online and len(interests.get()) > 4000: error.configure(text="Interests must be 4,000 characters or fewer."); return
            website_value = website.get().strip()
            if website_value and not re.match(r"^https?://", website_value, re.I): website_value = "https://" + website_value
            if online and len(website_value) > 255: error.configure(text="Your website or social link must be 255 characters or fewer."); return
            values = {"full_name": name.get(), "email": email_value, "zip": zip_value, "state": state_value,
                      "city": user.get("city", ""), "lat": user.get("lat"), "lng": user.get("lng"),
                      "bio": bio.get("1.0", "end-1c"), "interests": interests.get(),
                      "website": website_value, "avatar_path": avatar["path"]}
            visibility_values = {key: variable.get() for key, variable in visibility_vars.items()} if online else {}
            save_button.configure(state="disabled"); error.configure(text="Saving profile…", text_color=GOLD)
            def worker():
                try:
                    city, zip_state, lat, lng = (lookup_zip(zip_value) if not online or zip_value != str(user.get("zip") or "")
                                                  else (user.get("city", ""), state_value, user.get("lat"), user.get("lng")))
                    if zip_state and zip_state.upper() != state_value:
                        result = (False, f"That ZIP code belongs to {zip_state}.")
                    else:
                        same_zip = zip_value == str(user.get("zip") or "")
                        values.update({"state": zip_state or state_value, "city": city or (values["city"] if same_zip else ""),
                                       "lat": lat if lat is not None else (values["lat"] if same_zip else None),
                                       "lng": lng if lng is not None else (values["lng"] if same_zip else None)})
                        if online:
                            response = s.server_client.update_profile(s.server_access_token, {
                                "full_name": values["full_name"].strip(), "state": values["state"], "zip": zip_value,
                                "bio": values["bio"], "interests": values["interests"], "site": values["website"],
                                **visibility_values,
                            })
                            if avatar["dirty"]:
                                if avatar["remove"]:
                                    s.server_client.delete_profile_avatar(s.server_access_token)
                                elif avatar["path"]:
                                    s.server_client.upload_profile_avatar(s.server_access_token, avatar["path"])
                                response = s.server_client.get_profile(s.server_access_token)
                            result = (True, "Online profile saved.", response, city, lat, lng)
                        else:
                            result = database.update_user_profile(user["username"], values)
                except Exception as exc: result = (False, f"Could not save the profile: {exc}")
                s.app.uiq.put((s.finish_profile_update, (dialog, username, error, save_button, online, avatar["path"], *result)))
            threading.Thread(target=worker, daemon=True).start()
        save_button = ctk.CTkButton(form, text="Save profile", width=220, height=40, command=save); save_button.pack(pady=(6, 14))
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_profile_update(s, dialog, username, error, save_button, online, avatar_path, ok, message, response=None, city="", lat=None, lng=None):
        if not ok:
            try:
                if error.winfo_exists(): error.configure(text=message, text_color="#ff6b6b")
                if save_button.winfo_exists(): save_button.configure(state="normal")
            except Exception: pass
            return
        if online:
            account = dict(response or {})
            server_profile = account.get("profile") or {}
            s.user.update(account)
            s.user.update({
                "full_name": server_profile.get("full_name") or "",
                "display_name": server_profile.get("full_name") or username,
                "state": server_profile.get("state") or "",
                "zip": server_profile.get("zip") or "",
                "bio": server_profile.get("bio") or "",
                "interests": server_profile.get("interests") or "",
                "website": server_profile.get("site") or "",
                "city": city or s.user.get("city", ""),
                "lat": lat if lat is not None else s.user.get("lat"),
                "lng": lng if lng is not None else s.user.get("lng"),
                "avatar_path": avatar_path,
            })
            save_avatar_path(username, avatar_path)
        else:
            s.user = database.get_user(username)
        try:
            if dialog.winfo_exists(): dialog.destroy()
        except Exception: pass
        if s.winfo_ismapped(): s.show_dashboard(message)

    def show_community_hub(s):
        client = getattr(s, "server_client", None)
        token = getattr(s, "server_access_token", None)
        if not client or not token:
            messagebox.showinfo("Spotlight Community", "Create or sign in to an online Spotlight account to join the Community.", parent=s.winfo_toplevel())
            return
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Spotlight Community")
        dialog.geometry("940x700")
        dialog.minsize(760, 540)
        dialog.resizable(True, True)
        dialog.configure(fg_color=BG)
        dialog.transient(s.app)
        root = ctk.CTkFrame(dialog, fg_color=PANEL)
        root.pack(fill="both", expand=True, padx=16, pady=16)
        heading = ctk.CTkFrame(root, fg_color="transparent")
        heading.pack(fill="x", padx=12, pady=(12, 6))
        ctk.CTkLabel(heading, text="Spotlight Community", font=("Segoe UI", 25, "bold"), text_color=GOLD).pack(side="left")
        ctk.CTkLabel(heading, text=f"Member: {(s.user or {}).get('username', '')}", text_color="#9aa0b5").pack(side="right", padx=10)
        controls = ctk.CTkFrame(root, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=4)
        category_values = {"All topics": None, "General": "general", "Events": "events", "Music": "music",
                          "Movies & TV": "movies_tv", "Games": "games", "Sports": "sports", "Festivals": "festivals"}
        category = ctk.StringVar(value="All topics")
        ctk.CTkOptionMenu(controls, variable=category, values=list(category_values), width=160,
                          command=lambda _value: s.load_community_posts(client, token, dialog, posts, status,
                                                                        category_values[category.get()])).pack(side="left", padx=(0, 8))
        ctk.CTkButton(controls, text="Refresh", width=90,
                      command=lambda: s.load_community_posts(client, token, dialog, posts, status,
                                                             category_values[category.get()])).pack(side="left", padx=4)
        ctk.CTkButton(controls, text="＋ Start a discussion", width=170, fg_color="#9b6a1c", hover_color="#c48a2a",
                      command=lambda: s.create_community_post_dialog(client, token, dialog, category, category_values,
                                                                     posts, status)).pack(side="right", padx=4)
        if str((s.user or {}).get("role", "")).lower() == "admin":
            ctk.CTkButton(controls, text="Review reports", width=130, fg_color=CARD, hover_color=HOVER,
                          command=lambda: s.review_community_reports(client, token, dialog)).pack(side="right", padx=4)
            ctk.CTkButton(controls, text="Hidden content", width=125, fg_color=CARD, hover_color=HOVER,
                          command=lambda: s.review_hidden_community_content(client, token, dialog)).pack(side="right", padx=4)
        status = ctk.CTkLabel(root, text="Loading discussions…", text_color="#9aa0b5", anchor="w")
        status.pack(fill="x", padx=14, pady=(4, 6))
        posts = ctk.CTkScrollableFrame(root, fg_color="transparent")
        posts.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        s.load_community_posts(client, token, dialog, posts, status, None)
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def load_community_posts(s, client, token, dialog, view, status, category):
        try: status.configure(text="Loading discussions…", text_color="#9aa0b5")
        except Exception: return
        def worker():
            try: result = (True, client.list_community_posts(token, category=category))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_posts, (dialog, view, status, client, token, category, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_community_posts(s, dialog, view, status, client, token, category, ok, data):
        if not dialog.winfo_exists(): return
        for child in view.winfo_children(): child.destroy()
        if not ok:
            status.configure(text=f"Could not load Community: {data}", text_color="#ff6b6b")
            return
        status.configure(text=f"{len(data)} discussion{'s' if len(data) != 1 else ''} · Respectful conversation keeps Spotlight welcoming.",
                         text_color="#9aa0b5")
        if not data:
            ctk.CTkLabel(view, text="No discussions yet. Start the first one.", text_color="#9aa0b5",
                         font=("Segoe UI", 16)).pack(pady=28)
            return
        for post in data:
            card = ctk.CTkFrame(view, fg_color=CARD, corner_radius=12)
            card.pack(fill="x", padx=5, pady=5)
            meta = ctk.CTkFrame(card, fg_color="transparent")
            meta.pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(meta, text=post["category"].replace("_", " ").title(), text_color=GOLD,
                         font=("Segoe UI", 11, "bold")).pack(side="left")
            ctk.CTkLabel(meta, text=f"{post['author']} · {str(post['created_at'])[:16]}",
                         text_color="#85899a", font=("Segoe UI", 10)).pack(side="right")
            ctk.CTkLabel(card, text=post["title"], text_color="#e7e9f0",
                         font=("Segoe UI", 17, "bold"), anchor="w").pack(fill="x", padx=12, pady=(4, 0))
            excerpt = s.community_body_excerpt(post["body"], 260)
            ctk.CTkLabel(card, text=excerpt, text_color="#b6bbca", wraplength=820,
                         justify="left", anchor="w").pack(fill="x", padx=12, pady=(3, 4))
            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkButton(actions, text="View profile", width=105, height=30, fg_color="#24598a", hover_color="#3278b5",
                          command=lambda name=post["author"]: s.open_public_profile(client, token, name)).pack(side="left", padx=3)
            ctk.CTkButton(actions, text=f"Reply · {post['reply_count']}", width=150,
                          height=30, command=lambda item=post: s.open_community_thread(client, token, item,
                              (dialog, view, status, category))).pack(side="left", padx=3)
            ctk.CTkButton(actions, text="Report", width=70, height=30, fg_color="transparent", hover_color=HOVER,
                          command=lambda item=post: s.report_community_content(client, token, "post", item["id"])).pack(side="left", padx=3)
            if str((s.user or {}).get("role", "")).lower() == "admin":
                ctk.CTkButton(actions, text="Remove", width=80, height=30, fg_color="#812f39", hover_color="#a83b47",
                              command=lambda item=post: s.moderate_community_content(
                                  client, token, "post", item["id"], dialog,
                                  lambda: s.load_community_posts(client, token, dialog, view, status, category))).pack(side="left", padx=3)

    def create_community_post_dialog(s, client, token, board, category, category_values, posts, status):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Start a Community discussion")
        dialog.geometry("660x680")
        dialog.minsize(600, 620)
        dialog.resizable(True, True)
        dialog.configure(fg_color=BG)
        dialog.transient(board)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(panel, text="Start a discussion", font=("Segoe UI", 22, "bold"), text_color=GOLD).pack(anchor="w", padx=14, pady=(12, 6))
        topic = ctk.StringVar(value="general")
        ctk.CTkOptionMenu(panel, variable=topic,
                          values=["general", "events", "music", "movies_tv", "games", "sports", "festivals"],
                          width=180).pack(anchor="w", padx=14, pady=5)
        title = ctk.CTkEntry(panel, placeholder_text="Discussion title", width=520)
        title.pack(padx=14, pady=5)
        toolbar = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=8)
        toolbar.pack(fill="x", padx=14, pady=(7, 0))
        body = ctk.CTkTextbox(panel, width=590, height=300, wrap="word")
        editor = body._textbox
        body.pack(fill="both", expand=True, padx=14, pady=(0, 4))
        for tag, attrs in {
            "fmt_bold": {"font": ("Segoe UI", 13, "bold")},
            "fmt_italic": {"font": ("Segoe UI", 13, "italic")},
            "fmt_underline": {"underline": True},
        }.items():
            editor.tag_configure(tag, **attrs)
        def apply_tag(tag):
            try:
                start, end = editor.index("sel.first"), editor.index("sel.last")
                if tag in editor.tag_names(start): editor.tag_remove(tag, start, end)
                else: editor.tag_add(tag, start, end)
            except tk.TclError:
                message.configure(text="Select some text first, then choose a format.", text_color="#9aa0b5")
        ctk.CTkButton(toolbar, text="B", width=36, height=30, font=("Segoe UI", 13, "bold"),
                      command=lambda: apply_tag("fmt_bold")).pack(side="left", padx=(6, 2), pady=6)
        ctk.CTkButton(toolbar, text="I", width=36, height=30, font=("Segoe UI", 13, "italic"),
                      command=lambda: apply_tag("fmt_italic")).pack(side="left", padx=2, pady=6)
        ctk.CTkButton(toolbar, text="U", width=36, height=30, font=("Segoe UI", 13, "underline"),
                      command=lambda: apply_tag("fmt_underline")).pack(side="left", padx=2, pady=6)
        family = ctk.StringVar(value="Segoe UI")
        size = ctk.StringVar(value="13")
        families = ["Segoe UI", "Arial", "Georgia", "Times New Roman", "Courier New"]
        sizes = ["10", "11", "12", "13", "14", "16", "18", "20", "24"]
        def apply_font(*_):
            try:
                start, end = editor.index("sel.first"), editor.index("sel.last")
                tag = f"fmt_font_{family.get().replace(' ', '_')}_{size.get()}"
                existing = editor.tag_names(start)
                weight = "bold" if "fmt_bold" in existing else "normal"
                slant = "italic" if "fmt_italic" in existing else "roman"
                editor.tag_configure(tag, font=(family.get(), int(size.get()), weight, slant))
                editor.tag_add(tag, start, end)
            except (tk.TclError, ValueError):
                message.configure(text="Select some text first, then choose a font or size.", text_color="#9aa0b5")
        ctk.CTkOptionMenu(toolbar, variable=family, values=families, width=135, height=30,
                          command=lambda _v: apply_font()).pack(side="left", padx=4, pady=6)
        ctk.CTkOptionMenu(toolbar, variable=size, values=sizes, width=65, height=30,
                          command=lambda _v: apply_font()).pack(side="left", padx=2, pady=6)
        selected_photos = []
        photo_status = ctk.CTkLabel(panel, text="No photos attached · up to 4 JPEG, PNG, or WebP images",
                                    text_color="#9aa0b5", anchor="w")
        photo_status.pack(fill="x", padx=16, pady=(0, 2))
        def choose_photos():
            paths = filedialog.askopenfilenames(parent=dialog, title="Attach discussion photos",
                filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")])
            if paths:
                selected_photos[:] = list(paths[:4])
                photo_status.configure(text=f"{len(selected_photos)} photo{'s' if len(selected_photos) != 1 else ''} ready to upload")
                if len(paths) > 4: message.configure(text="A discussion can include up to four photos.", text_color=GOLD)
        ctk.CTkButton(toolbar, text="＋ Photo", width=86, height=30, fg_color="#24598a", hover_color="#3278b5",
                      command=choose_photos).pack(side="right", padx=6, pady=6)
        message = ctk.CTkLabel(panel, text="Keep it friendly. Posts are visible to Spotlight members.",
                               text_color="#9aa0b5", wraplength=500)
        message.pack(pady=5)
        submit = ctk.CTkButton(panel, text="Post discussion", width=180)
        def send():
            title_value = title.get().strip()
            body_value = s.serialize_community_rich_text(editor)
            if len(title_value) < 4 or (not body_value and not selected_photos):
                message.configure(text="Add a title (at least 4 characters) and text or a photo.", text_color="#ff6b6b")
                return
            if len(body_value) > 10000:
                message.configure(text="Your formatted message is too long. Shorten it and try again.", text_color="#ff6b6b")
                return
            submit.configure(state="disabled")
            message.configure(text="Posting…", text_color=GOLD)
            topic_value = topic.get()
            def worker():
                try:
                    post_result = client.create_community_post(token, topic_value, title_value,
                                                                body_value or "Photo attached.")
                    upload_error = ""
                    for path in selected_photos:
                        try: client.upload_community_image(token, post_result["id"], path)
                        except Exception as exc:
                            upload_error = str(exc)
                            break
                    result = (True, {"post": post_result, "image_error": upload_error})
                except Exception as exc: result = (False, str(exc))
                s.app.uiq.put((s.finish_community_post, (dialog, board, posts, status, client, token,
                                                          category, submit, message, *result)))
            threading.Thread(target=worker, daemon=True).start()
        submit.configure(command=send)
        submit.pack(pady=8)
        ctk.CTkButton(panel, text="Cancel", fg_color=CARD, hover_color=HOVER,
                      command=dialog.destroy).pack(pady=(0, 10))
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_community_post(s, form, board, posts, status, client, token, category, submit, message, ok, data):
        if not form.winfo_exists(): return
        if not ok:
            submit.configure(state="normal")
            message.configure(text=f"Could not post: {data}", text_color="#ff6b6b")
            return
        image_error = data.get("image_error", "") if isinstance(data, dict) else ""
        form.destroy()
        current = category.get()
        if image_error:
            messagebox.showwarning("Photo upload incomplete",
                f"Your discussion was posted, but at least one photo could not be uploaded.\n\n{image_error}",
                parent=board)
        s.load_community_posts(client, token, board, posts, status, {"All topics": None, "General": "general",
            "Events": "events", "Music": "music", "Movies & TV": "movies_tv", "Games": "games",
            "Sports": "sports", "Festivals": "festivals"}.get(current))

    def serialize_community_rich_text(s, editor):
        """Convert the editor's limited Tk formatting tags to safe inline HTML."""
        output, previous_style, run = [], None, []
        def flush():
            nonlocal run
            if not run: return
            value = "".join(run)
            escaped = escape(value).replace("\n", "<br>")
            output.append(f'<span style="{previous_style}">{escaped}</span>' if previous_style else escaped)
            run = []
        index, end = "1.0", editor.index("end-1c")
        while editor.compare(index, "<", end):
            char = editor.get(index, f"{index} + 1 chars")
            tags = editor.tag_names(index)
            style = []
            if "fmt_bold" in tags: style.append("font-weight:bold")
            if "fmt_italic" in tags: style.append("font-style:italic")
            if "fmt_underline" in tags: style.append("text-decoration:underline")
            for tag in tags:
                match = re.fullmatch(r"fmt_font_(Segoe_UI|Arial|Georgia|Times_New_Roman|Courier_New)_(\d+)", tag)
                if match:
                    family = match.group(1).replace("_", " ")
                    style.extend((f"font-family:{family}", f"font-size:{max(10, min(24, int(match.group(2))))}px"))
                    break
            style_value = ";".join(style)
            if style_value != previous_style:
                flush()
                previous_style = style_value
            run.append(char)
            index = editor.index(f"{index} + 1 chars")
        flush()
        return "".join(output).strip()

    def community_body_excerpt(s, content, limit):
        class PlainText(HTMLParser):
            def __init__(self): super().__init__(convert_charrefs=True); self.parts = []
            def handle_starttag(self, tag, attrs):
                if tag == "br": self.parts.append(" ")
            def handle_data(self, data): self.parts.append(data)
        parser = PlainText()
        try: parser.feed(str(content or "")); value = "".join(parser.parts)
        except Exception: value = unescape(re.sub(r"<[^>]*>", "", str(content or "")))
        value = " ".join(value.split())
        return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"

    def render_community_rich_text(s, parent, content, height=80, wraplength=640):
        """Render only the basic style markup produced by the Community editor."""
        widget = ctk.CTkTextbox(parent, height=height, wrap="word", fg_color="transparent",
                                text_color="#d4d7e1", border_width=0)
        text = widget._textbox
        class Renderer(HTMLParser):
            def __init__(self, target):
                super().__init__(convert_charrefs=True)
                self.target, self.active, self.stack, self.serial = target, [], [], 0
            def handle_starttag(self, tag, attrs):
                if tag == "br": self.target.insert("end", "\n", tuple(self.active)); return
                if tag not in {"b", "strong", "i", "em", "u", "span"}: return
                self.serial += 1
                name, options = f"community_render_{self.serial}", {}
                if tag in {"b", "strong"}: options["font"] = ("Segoe UI", 13, "bold")
                elif tag in {"i", "em"}: options["font"] = ("Segoe UI", 13, "italic")
                elif tag == "u": options["underline"] = True
                elif tag == "span":
                    style = dict(part.split(":", 1) for part in dict(attrs).get("style", "").split(";") if ":" in part)
                    family = style.get("font-family", "Segoe UI")
                    if family not in {"Segoe UI", "Arial", "Georgia", "Times New Roman", "Courier New"}: family = "Segoe UI"
                    try: size = max(10, min(24, int(style.get("font-size", "13px").replace("px", ""))))
                    except ValueError: size = 13
                    weight = "bold" if style.get("font-weight") == "bold" else "normal"
                    slant = "italic" if style.get("font-style") == "italic" else "roman"
                    options["font"] = (family, size, weight, slant)
                    if style.get("text-decoration") == "underline": options["underline"] = True
                self.target.tag_configure(name, **options)
                self.stack.append((tag, name))
                self.active.append(name)
            def handle_endtag(self, tag):
                for index in range(len(self.stack) - 1, -1, -1):
                    if self.stack[index][0] == tag:
                        del self.stack[index]
                        self.active = [name for _tag, name in self.stack]
                        break
            def handle_data(self, data): self.target.insert("end", data, tuple(self.active))
        try: Renderer(text).feed(str(content or ""))
        except Exception: text.insert("end", unescape(re.sub(r"<[^>]*>", "", str(content or ""))))
        text.configure(state="disabled")
        return widget

    def load_community_post_images(s, client, token, dialog, post, image_frame):
        def worker():
            try:
                images = client.list_community_images(token, post["id"])
                content = [(item, client.get_community_image(token, post["id"], item["id"])) for item in images]
                result = (True, content)
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_post_images, (dialog, image_frame, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_community_post_images(s, dialog, image_frame, ok, images):
        if not dialog.winfo_exists() or not image_frame.winfo_exists(): return
        for child in image_frame.winfo_children(): child.destroy()
        if not ok:
            ctk.CTkLabel(image_frame, text=f"Photos could not be loaded: {images}", text_color="#9aa0b5").pack(anchor="w")
            return
        for _metadata, data in images:
            try:
                with Image.open(BytesIO(data)) as source:
                    photo = ImageOps.contain(source.convert("RGB"), (300, 190))
                picture = ctk.CTkImage(light_image=photo, dark_image=photo, size=photo.size)
                s.imgs.append(picture)
                ctk.CTkLabel(image_frame, text="", image=picture).pack(side="left", padx=4, pady=4)
            except (OSError, ValueError):
                ctk.CTkLabel(image_frame, text="Photo unavailable", text_color="#9aa0b5").pack(side="left", padx=4)

    def open_community_thread(s, client, token, post, board_context=None):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title(post["title"])
        dialog.geometry("760x680")
        dialog.minsize(620, 500)
        dialog.resizable(True, True)
        dialog.configure(fg_color=BG)
        dialog.transient(board_context[0] if board_context else s.app)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        # Reserve bottom space for the reply composer before packing the variable-height post content.
        composer = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=10)
        composer.pack(side="bottom", fill="x", padx=8, pady=(4, 8))
        ctk.CTkLabel(composer, text="Write a reply", text_color="#cfd3e0",
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(7, 0))
        reply_box = ctk.CTkTextbox(composer, height=96, wrap="word")
        reply_box.pack(fill="x", padx=8, pady=(3, 2))
        status = ctk.CTkLabel(composer, text="", text_color="#9aa0b5")
        status.pack(anchor="w", padx=10, pady=(0, 2))
        send = ctk.CTkButton(composer, text="Reply", width=110,
                             command=lambda: s.submit_community_reply(client, token, dialog, post, replies,
                                                                      reply_box, send, status))
        send.pack(anchor="e", padx=8, pady=(0, 8))
        ctk.CTkLabel(panel, text=post["title"], font=("Segoe UI", 20, "bold"), text_color=GOLD,
                     wraplength=680, justify="left").pack(anchor="w", padx=12, pady=(10, 3))
        ctk.CTkLabel(panel, text=f"{post['category'].replace('_', ' ').title()} · {str(post['created_at'])[:16]}",
                     text_color="#85899a").pack(anchor="w", padx=12)
        ctk.CTkButton(panel, text=f"Posted by {post['author']} · View profile", width=220, height=26,
                      fg_color="transparent", hover_color=HOVER,
                      command=lambda: s.open_public_profile(client, token, post["author"])).pack(anchor="w", padx=8, pady=(2, 0))
        ctk.CTkLabel(panel, text="Original post", text_color="#cfd3e0",
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(8, 0))
        s.render_community_rich_text(panel, post["body"], height=250, wraplength=680).pack(fill="x", padx=12, pady=(3, 4))
        image_frame = ctk.CTkFrame(panel, fg_color="transparent")
        image_frame.pack(fill="x", padx=10, pady=(0, 6))
        s.load_community_post_images(client, token, dialog, post, image_frame)
        ctk.CTkButton(panel, text="Report discussion", width=150, height=30, fg_color="transparent", hover_color=HOVER,
                      command=lambda: s.report_community_content(client, token, "post", post["id"])).pack(anchor="w", padx=8, pady=(0, 6))
        if str((s.user or {}).get("role", "")).lower() == "admin":
            def remove_post_from_thread():
                callback = None
                if board_context:
                    board, board_view, board_status, board_category = board_context
                    callback = lambda: s.load_community_posts(client, token, board, board_view, board_status, board_category)
                s.moderate_community_content(client, token, "post", post["id"], dialog, callback)
            ctk.CTkButton(panel, text="Remove discussion", width=150, height=30, fg_color="#812f39",
                          hover_color="#a83b47", command=remove_post_from_thread).pack(anchor="w", padx=8, pady=(0, 6))
        ctk.CTkLabel(panel, text="Replies", text_color="#cfd3e0",
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(4, 0))
        replies = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        replies.pack(fill="both", expand=True, padx=6, pady=4)
        s.load_community_replies(client, token, dialog, post, replies, status)
        dialog.after(100, lambda: (dialog.deiconify(), dialog.lift(), dialog.focus_force()))

    def load_community_replies(s, client, token, dialog, post, view, status):
        def worker():
            try: result = (True, client.list_community_replies(token, post["id"]))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_replies, (dialog, post, view, status, client, token, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_community_replies(s, dialog, post, view, status, client, token, ok, data):
        if not dialog.winfo_exists(): return
        for child in view.winfo_children(): child.destroy()
        if not ok:
            status.configure(text=f"Could not load replies: {data}", text_color="#ff6b6b")
            return
        if not data:
            ctk.CTkLabel(view, text="No replies yet.", text_color="#9aa0b5").pack(pady=12)
        for reply in data:
            card = ctk.CTkFrame(view, fg_color=CARD, corner_radius=10)
            card.pack(fill="x", padx=5, pady=4)
            ctk.CTkButton(card, text=f"{reply['author']} · {str(reply['created_at'])[:16]} · View profile",
                          text_color=GOLD, fg_color="transparent", hover_color=HOVER,
                          font=("Segoe UI", 10, "bold"), height=24, width=300,
                          command=lambda name=reply["author"]: s.open_public_profile(client, token, name)).pack(anchor="w", padx=6, pady=(5, 0))
            ctk.CTkLabel(card, text=reply["body"], text_color="#cfd3e0", wraplength=640,
                         justify="left", anchor="w").pack(fill="x", padx=10, pady=4)
            ctk.CTkButton(card, text="Report reply", width=100, height=26, fg_color="transparent", hover_color=HOVER,
                          command=lambda item=reply: s.report_community_content(client, token, "reply", item["id"])).pack(anchor="w", padx=6, pady=(0, 4))
            if str((s.user or {}).get("role", "")).lower() == "admin":
                ctk.CTkButton(card, text="Remove reply", width=100, height=26, fg_color="#812f39", hover_color="#a83b47",
                              command=lambda item=reply: s.moderate_community_content(
                                  client, token, "reply", item["id"], dialog,
                                  lambda: s.load_community_replies(client, token, dialog, post, view, status))).pack(anchor="w", padx=6, pady=(0, 5))
        status.configure(text=f"{len(data)} {'reply' if len(data) == 1 else 'replies'}", text_color="#9aa0b5")

    def open_public_profile(s, client, token, username):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title(f"{username} · Spotlight member")
        dialog.geometry("460x560")
        dialog.minsize(400, 460)
        dialog.resizable(True, True)
        dialog.configure(fg_color=BG)
        dialog.transient(s.app)
        panel = ctk.CTkScrollableFrame(dialog, fg_color=PANEL, corner_radius=14)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        status = ctk.CTkLabel(panel, text="Loading member profile…", text_color="#9aa0b5")
        status.pack(pady=24)
        def worker():
            try:
                profile = client.get_public_profile(token, username)
                photo = client.get_public_profile_avatar(token, username) if profile.get("avatar_url") else None
                result = (True, profile, photo)
            except Exception as exc:
                result = (False, str(exc), None)
            s.app.uiq.put((s.finish_public_profile, (dialog, panel, status, *result)))
        threading.Thread(target=worker, daemon=True).start()
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_public_profile(s, dialog, panel, status, ok, profile, photo):
        if not dialog.winfo_exists(): return
        status.destroy()
        if not ok:
            ctk.CTkLabel(panel, text="This member profile could not be loaded.",
                         font=("Segoe UI", 17, "bold"), text_color="#ff6b6b",
                         wraplength=390).pack(padx=20, pady=(30, 8))
            ctk.CTkLabel(panel, text=f"{profile}", text_color="#cfd3e0",
                         wraplength=390, justify="center").pack(padx=20, pady=5)
            ctk.CTkLabel(panel, text="The profile service may need to be updated on the SpotLight server.",
                         text_color="#9aa0b5", wraplength=390, justify="center").pack(padx=20, pady=8)
            ctk.CTkButton(panel, text="Close", width=120, command=dialog.destroy).pack(pady=18)
            return
        if photo:
            try:
                with Image.open(BytesIO(photo)) as source:
                    image = ImageOps.fit(source.convert("RGB"), (144, 144))
                picture = ctk.CTkImage(light_image=image, dark_image=image, size=(144, 144))
                s.imgs.append(picture)
                ctk.CTkLabel(panel, image=picture, text="", corner_radius=72).pack(pady=(20, 8))
            except Exception:
                pass
        ctk.CTkLabel(panel, text=profile.get("display_name") or profile.get("username"),
                     font=("Segoe UI", 23, "bold"), text_color=GOLD).pack(pady=(12, 3))
        role = "Administrator" if str(profile.get("role", "")).lower() == "admin" else "Spotlight member"
        ctk.CTkLabel(panel, text=f"@{profile.get('username', '')}  ·  {role}", text_color="#cfd3e0").pack(pady=2)
        joined = str(profile.get("created_at", ""))[:10]
        if joined:
            ctk.CTkLabel(panel, text=f"Joined {joined}", text_color="#9aa0b5").pack(pady=(2, 10))
        for key, label in (("state", "Location"), ("bio", "About"), ("interests", "Interests"), ("site", "Website / social")):
            value = profile.get(key)
            if value:
                row = ctk.CTkFrame(panel, fg_color="transparent")
                row.pack(fill="x", padx=18, pady=4)
                ctk.CTkLabel(row, text=label, width=115, anchor="w", text_color=GOLD,
                             font=("Segoe UI", 11, "bold")).pack(side="left", anchor="n")
                ctk.CTkLabel(row, text=str(value), text_color="#d4d7e1", wraplength=270,
                             justify="left", anchor="w").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(panel, text="Close", width=120, command=dialog.destroy).pack(pady=(16, 12))

    def moderate_community_content(s, client, token, target_type, target_id, parent, on_success=None):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Remove Community content")
        dialog.geometry("480x300")
        dialog.configure(fg_color=BG)
        dialog.transient(parent)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(panel, text="Hide this content from members?", font=("Segoe UI", 18, "bold"),
                     text_color=GOLD).pack(pady=(14, 5))
        ctk.CTkLabel(panel, text="The action is recorded for moderation review and can be reversed by an administrator.",
                     text_color="#9aa0b5", wraplength=400, justify="center").pack(padx=15, pady=5)
        reason = ctk.CTkEntry(panel, placeholder_text="Reason (optional)", width=390)
        reason.pack(pady=8)
        status = ctk.CTkLabel(panel, text="", text_color="#9aa0b5")
        status.pack(pady=3)
        button = ctk.CTkButton(panel, text="Hide content", width=150, fg_color="#812f39", hover_color="#a83b47")
        def submit():
            button.configure(state="disabled")
            status.configure(text="Saving moderation action…", text_color=GOLD)
            reason_text = reason.get().strip()
            def worker():
                try:
                    client.moderate_community_content(token, target_type, target_id, "hide", reason_text)
                    result = (True, "Content hidden.")
                except Exception as exc:
                    result = (False, str(exc))
                s.app.uiq.put((s.finish_community_content_moderation,
                               (dialog, parent, status, button, target_type, on_success, *result)))
            threading.Thread(target=worker, daemon=True).start()
        button.configure(command=submit)
        button.pack(pady=5)
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_community_content_moderation(s, dialog, parent, status, button, target_type, on_success, ok, message):
        if not dialog.winfo_exists(): return
        if not ok:
            status.configure(text=f"Could not hide content: {message}", text_color="#ff6b6b")
            button.configure(state="normal")
            return
        dialog.destroy()
        if parent.winfo_exists():
            if target_type == "post" and not str(parent.title()).startswith("Spotlight Community"):
                parent.destroy()
                if on_success: on_success()
            elif on_success:
                on_success()
        else: messagebox.showinfo("Spotlight Community", message, parent=parent)

    def submit_community_reply(s, client, token, dialog, post, replies, reply_box, button, status):
        body = reply_box.get("1.0", "end-1c").strip()
        if not body:
            status.configure(text="Write a reply first.", text_color="#ff6b6b")
            return
        button.configure(state="disabled")
        status.configure(text="Posting reply…", text_color=GOLD)
        def worker():
            try: result = (True, client.create_community_reply(token, post["id"], body))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_reply, (dialog, post, replies, reply_box, button, status, client, token, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_community_reply(s, dialog, post, replies, reply_box, button, status, client, token, ok, data):
        if not dialog.winfo_exists(): return
        button.configure(state="normal")
        if not ok:
            status.configure(text=f"Could not post reply: {data}", text_color="#ff6b6b")
            return
        reply_box.delete("1.0", "end")
        status.configure(text="Reply posted.", text_color="#77d18b")
        s.load_community_replies(client, token, dialog, post, replies, status)

    def report_community_content(s, client, token, target_type, target_id):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Report Community content")
        dialog.geometry("470x270")
        dialog.configure(fg_color=BG)
        dialog.transient(s.app)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(panel, text="Report this content", font=("Segoe UI", 19, "bold"), text_color=GOLD).pack(pady=(12, 6))
        reason = ctk.CTkEntry(panel, placeholder_text="Briefly tell moderators why", width=390)
        reason.pack(pady=8)
        status = ctk.CTkLabel(panel, text="", text_color="#9aa0b5", wraplength=390)
        status.pack(pady=5)
        send = ctk.CTkButton(panel, text="Send report", width=150)
        def submit():
            text = reason.get().strip()
            if len(text) < 5:
                status.configure(text="Please add a short reason (at least 5 characters).", text_color="#ff6b6b")
                return
            send.configure(state="disabled")
            status.configure(text="Sending report…", text_color=GOLD)
            def worker():
                try: result = (True, client.report_community_content(token, target_type, target_id, text).get("message", "Report sent."))
                except Exception as exc: result = (False, str(exc))
                s.app.uiq.put((s.finish_community_report, (dialog, send, status, *result)))
            threading.Thread(target=worker, daemon=True).start()
        send.configure(command=submit)
        send.pack(pady=5)
        dialog.after(50, lambda: (dialog.lift(), dialog.focus_force()))

    def finish_community_report(s, dialog, button, status, ok, message):
        if not dialog.winfo_exists(): return
        status.configure(text=message, text_color="#77d18b" if ok else "#ff6b6b")
        if ok: button.configure(text="Sent", state="disabled")
        else: button.configure(state="normal")

    def review_community_reports(s, client, token, board):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Community reports for review")
        dialog.geometry("760x620")
        dialog.resizable(True, True)
        dialog.configure(fg_color=BG)
        dialog.transient(board)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(panel, text="Moderator review", font=("Segoe UI", 22, "bold"), text_color=GOLD).pack(anchor="w", padx=12, pady=(10, 4))
        status = ctk.CTkLabel(panel, text="Loading reports…", text_color="#9aa0b5", anchor="w")
        status.pack(fill="x", padx=12)
        view = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        view.pack(fill="both", expand=True, padx=6, pady=6)
        def worker():
            try: result = (True, client.list_community_reports(token))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_reports, (dialog, view, status, client, token, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def review_hidden_community_content(s, client, token, board):
        dialog = ctk.CTkToplevel(s.app)
        dialog.title("Hidden Community content")
        dialog.geometry("720x600")
        dialog.resizable(True, True)
        dialog.configure(fg_color=BG)
        dialog.transient(board)
        panel = ctk.CTkFrame(dialog, fg_color=PANEL)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(panel, text="Hidden content", font=("Segoe UI", 21, "bold"), text_color=GOLD).pack(anchor="w", padx=12, pady=(10, 4))
        status = ctk.CTkLabel(panel, text="Loading…", text_color="#9aa0b5", anchor="w")
        status.pack(fill="x", padx=12)
        view = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        view.pack(fill="both", expand=True, padx=6, pady=6)
        def worker():
            try: result = (True, client.list_hidden_community_content(token))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_hidden_community_content, (dialog, view, status, client, token, board, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_hidden_community_content(s, dialog, view, status, client, token, board, ok, data):
        if not dialog.winfo_exists(): return
        for child in view.winfo_children(): child.destroy()
        if not ok:
            status.configure(text=f"Could not load hidden content: {data}", text_color="#ff6b6b")
            return
        status.configure(text=f"{len(data)} hidden item{'s' if len(data) != 1 else ''}", text_color="#9aa0b5")
        if not data:
            ctk.CTkLabel(view, text="There are no hidden discussions or replies.", text_color="#9aa0b5").pack(pady=24)
            return
        for item in data:
            card = ctk.CTkFrame(view, fg_color=CARD, corner_radius=10)
            card.pack(fill="x", padx=5, pady=5)
            heading = f"{item['target_type'].title()} · {item.get('author', 'Member')} · {str(item.get('created_at', ''))[:10]}"
            ctk.CTkLabel(card, text=heading, text_color=GOLD, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 1))
            ctk.CTkLabel(card, text=item.get("title", ""), text_color="#e7e9f0", font=("Segoe UI", 14, "bold"),
                         wraplength=620, justify="left", anchor="w").pack(fill="x", padx=10, pady=2)
            excerpt = item.get("body", "")
            if len(excerpt) > 220: excerpt = excerpt[:217].rstrip() + "…"
            ctk.CTkLabel(card, text=excerpt, text_color="#b6bbca", wraplength=620,
                         justify="left", anchor="w").pack(fill="x", padx=10, pady=2)
            ctk.CTkButton(card, text="Restore", width=95, height=28, fg_color="#276b48", hover_color="#34885d",
                          command=lambda record=item: s.restore_community_content(
                              client, token, dialog, view, status, board, record)).pack(anchor="e", padx=8, pady=(2, 8))

    def restore_community_content(s, client, token, dialog, view, status, board, item):
        status.configure(text="Restoring content…", text_color=GOLD)
        def worker():
            try:
                client.moderate_community_content(token, item["target_type"], item["id"], "restore")
                result = (True, client.list_hidden_community_content(token))
            except Exception as exc:
                result = (False, str(exc))
            s.app.uiq.put((s.finish_hidden_community_content, (dialog, view, status, client, token, board, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_community_reports(s, dialog, view, status, client, token, ok, reports):
        if not dialog.winfo_exists(): return
        for child in view.winfo_children(): child.destroy()
        if not ok:
            status.configure(text=f"Could not load reports: {reports}", text_color="#ff6b6b")
            return
        status.configure(text=f"{len(reports)} pending report{'s' if len(reports) != 1 else ''}", text_color="#9aa0b5")
        if not reports:
            ctk.CTkLabel(view, text="No reports need review.", text_color="#9aa0b5").pack(pady=24)
        for report in reports:
            card = ctk.CTkFrame(view, fg_color=CARD, corner_radius=10)
            card.pack(fill="x", padx=5, pady=5)
            content = report.get("content", {})
            ctk.CTkLabel(card, text=f"{report['target_type'].title()} · reported by {report['reporter']}",
                         text_color=GOLD, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=content.get("title", content.get("body", "")), text_color="#d4d7e1",
                         wraplength=640, justify="left", anchor="w").pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(card, text=f"Report: {report['reason']}", text_color="#9aa0b5",
                         wraplength=640, justify="left", anchor="w").pack(fill="x", padx=10, pady=2)
            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.pack(anchor="e", padx=8, pady=(2, 8))
            for action, label in (("dismiss", "Dismiss"), ("hide", "Hide content")):
                ctk.CTkButton(actions, text=label, width=120,
                              fg_color=CARD if action == "dismiss" else "#812f39",
                              command=lambda item=report, choice=action: s.moderate_community_report(
                                  client, token, dialog, view, status, item, choice)).pack(side="left", padx=3)

    def moderate_community_report(s, client, token, dialog, view, status, report, action):
        status.configure(text="Saving moderator decision…", text_color=GOLD)
        def worker():
            try: result = (True, client.moderate_community_report(token, report["id"], action).get("status", "reviewed"))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_moderation, (dialog, view, status, client, token, *result)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_community_moderation(s, dialog, view, status, client, token, ok, message):
        if not dialog.winfo_exists(): return
        if not ok:
            status.configure(text=f"Could not save review: {message}", text_color="#ff6b6b")
            return
        def worker():
            try: result = (True, client.list_community_reports(token))
            except Exception as exc: result = (False, str(exc))
            s.app.uiq.put((s.finish_community_reports, (dialog, view, status, client, token, *result)))
        status.configure(text="Review saved.", text_color="#77d18b")
        threading.Thread(target=worker, daemon=True).start()

    def sign_out(s):
        if s.auto_refresh_after_id is not None:
            try: s.after_cancel(s.auto_refresh_after_id)
            except Exception: pass
            s.auto_refresh_after_id = None
        s.auto_refresh_started = False
        s.user = None
        s.app.reset_session_view()
        s.show_login()
