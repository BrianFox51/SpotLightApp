"""Curator tool: review submitted events and maintain the public events.json feed you host (for example on GitHub).
  python curator.py add submission.json [more.json ...]   check + merge submissions (private fields are stripped from the public feed)
  python curator.py list                                   show what is in events.json
  python curator.py remove EVENT_ID                        take an event down
  python curator.py prune                                  drop events that ended more than 7 days ago
Use  --file path/to/events.json  to work on a different feed file. Always open the organizer's link and make sure the event is real before you publish."""
import sys, json, datetime
import community

args = sys.argv[1:]; path = "events.json"
if "--file" in args: i = args.index("--file"); path = args[i + 1]; del args[i:i + 2]


def load():
    try:
        with open(path, encoding="utf-8") as f: d = json.load(f)
        return d.get("events", []) if isinstance(d, dict) else d
    except FileNotFoundError: return []


def save(evs):
    evs = sorted(evs, key=lambda e: (e["date"], e["title"]))
    with open(path, "w", encoding="utf-8") as f: json.dump({"version": 1, "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "events": evs}, f, indent=1, ensure_ascii=False)
    print(f"Saved {len(evs)} events to {path}. Commit and push it to publish.")


def main():
    cmd = args[0] if args else ""; evs = load(); by = {e["id"]: e for e in evs}
    if cmd == "add":
        for fn in args[1:]:
            with open(fn, encoding="utf-8") as f: data = json.load(f)
            for it in data if isinstance(data, list) else [data]:
                e, errs = community.validate(it, need_email=False)
                if errs: print("SKIPPED", it.get("title"), "->", "; ".join(errs)); continue
                print(("UPDATED" if e["id"] in by else "ADDED  "), e["id"], e["date"], e["title"], "| verify link:", e["ticket_url"], "| contact:", it.get("contact_email", "(none)"))
                by[e["id"]] = community.public(e)
        save(list(by.values()))
    elif cmd == "list":
        for e in sorted(evs, key=lambda e: e["date"]): print(e["id"], e["date"], e["category"], e["title"], "-", e["city"] + ", " + e["state"])
    elif cmd == "remove" and len(args) > 1:
        if args[1] in by: del by[args[1]]; save(list(by.values()))
        else: print("No such id.")
    elif cmd == "prune":
        cut = (datetime.date.today() - datetime.timedelta(days=7)).isoformat(); keep = [e for e in evs if (e.get("end_date") or e["date"]) >= cut]
        print(f"Removed {len(evs) - len(keep)} ended events."); save(keep)
    else: print(__doc__)


main()
