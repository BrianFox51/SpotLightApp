"""In-app 'Promote your event' form: free founding listings for local sports, fairs and festivals."""
import json, webbrowser, tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
import community

BG, CARD, HOVER, GOLD = "#0b0b11", "#1a1a26", "#28283e", "#c9a45c"


class PromoteForm(ctk.CTkFrame):
    def __init__(s, app, host):
        super().__init__(host.master, fg_color=BG, corner_radius=0)
        s.app, s.f, s.ev = app, {}, None
        s.place(in_=host, x=0, y=0, relwidth=1, relheight=1)
        ctk.CTkButton(s, text="‹  Back", width=90, fg_color=CARD, hover_color=HOVER, command=s.close).pack(anchor="w", padx=24, pady=(16, 4))
        s.body = ctk.CTkScrollableFrame(s, fg_color="transparent"); s.body.pack(fill="both", expand=True, padx=10)
        s.build()

    def close(s): s.app.close_promote()

    def row(s): r = ctk.CTkFrame(s.body, fg_color="transparent"); r.pack(fill="x", padx=14, pady=3); return r

    def field(s, row, key, label, ph="", width=230):
        c = ctk.CTkFrame(row, fg_color="transparent"); c.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(c, text=label, anchor="w", text_color="#9aa0b5", font=("Segoe UI", 12)).pack(anchor="w")
        e = ctk.CTkEntry(c, width=width, placeholder_text=ph); e.pack(); s.f[key] = e

    def build(s):
        b = s.body
        ctk.CTkLabel(b, text="📣  Promote your event", font=("Segoe UI", 30, "bold")).pack(anchor="w", padx=14, pady=(4, 0))
        ctk.CTkLabel(b, text="Free listings for local sports, fairs and festivals. A registered Spotlight profile is required. A curator reviews each listing before it goes live. For the same event date, approved user submissions appear above third-party listings; user submissions are ordered first-come, first-served by submission time.",
                     wraplength=760, justify="left", anchor="w", text_color="#9aa0b5").pack(anchor="w", padx=14, pady=(0, 10))
        if not (getattr(s.app.gate, "user", None) or {}).get("username"):
            ctk.CTkLabel(b, text="Sign in with a registered Spotlight profile to submit an event.",
                         text_color="#f0cf78", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(0, 8))
        r = s.row(); s.field(r, "title", "Event name *", "Circleville Pumpkin Show", 480)
        r = s.row(); ctk.CTkLabel(r, text="Category *", text_color="#9aa0b5", font=("Segoe UI", 12)).pack(anchor="w")
        r = s.row(); s.cat = ctk.CTkSegmentedButton(r, values=list(community.CAT_NAMES.values()), command=s.set_cat); s.cat.pack(side="left", padx=(0, 12))
        s.type = ctk.CTkOptionMenu(r, values=community.TYPES["festivals"], width=220); s.type.pack(side="left"); s.cat.set(community.CAT_NAMES["festivals"])
        r = s.row(); s.field(r, "date", "Start date * (YYYY-MM-DD)", "2026-10-21", 170); s.field(r, "end_date", "End date (optional)", "2026-10-24", 170); s.field(r, "time", "Start time (24h, optional)", "19:30", 150); s.field(r, "price", "Price (optional)", "Free / $10", 130)
        r = s.row(); s.field(r, "venue", "Venue *", "Pickaway County Fairgrounds", 300); s.field(r, "address", "Street address (optional)", "", 280)
        r = s.row(); s.field(r, "city", "City *", "", 220); s.field(r, "state", "State * (2 letters)", "OH", 90)
        r = s.row(); s.field(r, "ticket_url", "Ticket / info link * (https://…)", "https://", 400); s.field(r, "image_url", "Poster image link (optional)", "https://", 300)
        ctk.CTkLabel(b, text="Description * (20–1200 characters)", anchor="w", text_color="#9aa0b5", font=("Segoe UI", 12)).pack(anchor="w", padx=14, pady=(8, 0))
        s.desc = ctk.CTkTextbox(b, height=100, fg_color=CARD); s.desc.pack(fill="x", padx=14)
        r = s.row(); s.field(r, "organizer", "Organizer name *", "", 260); s.field(r, "contact_email", "Contact email * (never shown publicly)", "", 320)
        s.ok = ctk.CTkCheckBox(b, text="I am authorized to promote this event and allow SpotLight to display it."); s.ok.pack(anchor="w", padx=14, pady=(10, 4))
        s.msg = ctk.CTkLabel(b, text="", anchor="w", justify="left", wraplength=760, text_color="#ff6b6b"); s.msg.pack(anchor="w", padx=14)
        ctk.CTkButton(b, text="Submit event", width=180, height=40, font=("Segoe UI", 15, "bold"), command=s.submit).pack(anchor="w", padx=14, pady=8)
        s.after_box = ctk.CTkFrame(b, fg_color="transparent"); s.after_box.pack(fill="x", padx=14)
        ctk.CTkLabel(b, text="My submissions", font=("Segoe UI", 20, "bold"), anchor="w").pack(anchor="w", padx=14, pady=(18, 4))
        s.mine = ctk.CTkFrame(b, fg_color="transparent"); s.mine.pack(fill="x", padx=14, pady=(0, 20)); s.refresh()

    def set_cat(s, name):
        key = next(k for k, v in community.CAT_NAMES.items() if v == name); vals = community.TYPES[key]; s.type.configure(values=vals); s.type.set(vals[0])

    def submit(s):
        if not (getattr(s.app.gate, "user", None) or {}).get("username"):
            s.msg.configure(text="Sign in with a registered Spotlight profile before submitting an event."); return
        form = {k: w.get().strip() for k, w in s.f.items()}; form["description"] = s.desc.get("1.0", "end").strip()
        form["category"] = next(k for k, v in community.CAT_NAMES.items() if v == s.cat.get()); form["type"] = s.type.get()
        if not s.ok.get(): s.msg.configure(text="Please tick the box to confirm you may promote this event."); return
        ev, errs = community.validate(form)
        if errs: s.msg.configure(text="\n".join("• " + x for x in errs)); return
        s.msg.configure(text=""); ev = community.add_mine(ev)
        s.app.apply_community({"meta": community.save_events([ev], s.app.poster_dir(), "Community (pending)")}); s.ev = ev; s.result(ev); s.refresh()

    def result(s, ev):
        for w in s.after_box.winfo_children(): w.destroy()
        ctk.CTkLabel(s.after_box, text="✅  Saved! It now shows in your own SpotLight (Sports / Festivals). To publish it for everyone, send it to the curator:",
                     wraplength=760, justify="left", anchor="w", text_color="#6fdc8c").pack(anchor="w")
        r = ctk.CTkFrame(s.after_box, fg_color="transparent"); r.pack(anchor="w", pady=6)
        mail = community.submit_email()
        ctk.CTkButton(r, text="✉  Email to curator", command=lambda: webbrowser.open(community.mailto(ev)), state="normal" if mail else "disabled").pack(side="left", padx=(0, 8))
        ctk.CTkButton(r, text="📋  Copy event data", fg_color=CARD, hover_color=HOVER, command=lambda: (s.clipboard_clear(), s.clipboard_append(json.dumps(ev, indent=1, ensure_ascii=False)))).pack(side="left", padx=8)
        ctk.CTkButton(r, text="💾  Save as file", fg_color=CARD, hover_color=HOVER, command=lambda: s.save_file(ev)).pack(side="left", padx=8)
        if not mail: ctk.CTkLabel(s.after_box, text="(The curator email isn't set up yet. Use Copy or Save and send the data to the SpotLight team.)", text_color="#9aa0b5", anchor="w").pack(anchor="w")

    def save_file(s, ev):
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="spotlight-event-" + ev["id"] + ".json", filetypes=[("JSON", "*.json")])
        if p:
            with open(p, "w", encoding="utf-8") as f: json.dump(ev, f, indent=1, ensure_ascii=False)

    def refresh(s):
        for w in s.mine.winfo_children(): w.destroy()
        live = community.live_ids(); mine = community.load_mine()
        if not mine: ctk.CTkLabel(s.mine, text="Nothing yet.", text_color="#888").pack(anchor="w")
        for x in mine:
            r = ctk.CTkFrame(s.mine, fg_color=CARD, corner_radius=10); r.pack(fill="x", pady=3); st = "Live for everyone ✓" if x["id"] in live else "Waiting for review"
            ctk.CTkLabel(r, text=f"{x['title']}   ·   {x['date']}   ·   {x['city']}, {x['state']}", anchor="w").pack(side="left", padx=12, pady=8)
            ctk.CTkButton(r, text="✕", width=34, fg_color="transparent", hover_color=HOVER, command=lambda i=x["id"]: (community.remove_mine(i), s.refresh())).pack(side="right", padx=6)
            ctk.CTkLabel(r, text=st, text_color="#6fdc8c" if x["id"] in live else GOLD).pack(side="right", padx=8)
