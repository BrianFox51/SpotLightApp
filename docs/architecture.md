# SpotLightApp architecture and file map

## Startup and program flow

1. `main.py` imports the application modules, sets up project-relative media folders, defines category and display helpers, and defines the `App` window.
2. `App.__init__` loads display metadata, seeds demo catalog entries once, builds the interface, starts background connection monitoring, and creates the sign-in/dashboard gate.
3. `dashboard.Gate` handles guest access, separate online account registration and local profile creation, server-first sign-in, optional same-PC offline sign-in for previously verified online accounts, account recovery, profile display/editing, dashboard statistics, API credential editing/status, and the combined Refresh action. Server registration, sign-in, profile retrieval, public member profiles, profile photo upload, and profile updates use `server_client.py`. The dashboard still requires manual refresh; automatic refresh and interactive statistic quick links are planned.
4. The catalog is read from SQLite through `database.py`. Selecting a title displays its local metadata, cast/crew, events, and notes. Spotlight Search stays available above the content and searches saved catalog fields across all categories or the current category.
5. `online.py` retrieves missing details in background threads. It also syncs TMDB theatrical/airing catalogs and a bounded Watchmode U.S. streaming catalog; per-title Watchmode provider links are requested on demand. `main.py` returns results to the UI thread through a queue.
6. `events.py` syncs Ticketmaster events; `community.py` syncs an optional organizer feed. The `promote.py` form lets an organizer prepare a submission for curator review.

## Active Python files

### `main.py`

The application entry point and primary UI controller. It owns navigation, media cards and detail views, Spotlight Search, generated artwork and motion backgrounds, trailer controls, notes, and the coordination of background lookup/sync jobs. Search ranks local matches from titles, descriptions, years, artists, event types, and other saved metadata; it displays up to 25 results per page. Category filters with no matching items are hidden. It imports the modules below. It also seeds example rows in the local catalog when its metadata flag is absent.

### `database.py`

Creates and accesses SQLite tables for media items, cast/crew, local events, local users, locally cached offline credentials for previously verified server accounts, and local favorites. It hashes passwords with per-account salts, saves notes, and provides catalog/dashboard queries. Dashboard counts currently sum catalog rows by database category; the state-specific dashboard value currently counts local events despite its “Titles in [state]” label. See `docs/frontend-backend-integration.md` for the count/cache audit and ownership rules. The database is stored under the current user's `.spotlight` directory, not beside the Python files.

### `dashboard.py`

Implements the sign-in/create-account/guest screen and the dashboard shown after entry. It uses the database for account operations and statistics, and `events.py` for local event configuration and sync controls.

### `server_client.py`

Small HTTP client for the optional backend. Reads a saved server address from `~/.spotlight/config.json`, uses the home-beta default when none is saved, and accepts `SPOTLIGHT_API_BASE_URL` as a development override. It sends JSON or multipart requests, attaches bearer access tokens for protected calls, and translates HTTP/network failures into `ServerAPIError`. The desktop uses account registration/login, profile retrieval/update and visibility controls, public profile/photo retrieval, Community discussions, reports, and admin moderation; token refresh/revocation and server favorites methods are not yet wired to the UI.

### `online.py`

Contains HTTP helpers and provider integrations. Its code can retrieve title/artist information and artwork from Apple search, Steam, TMDB, Wikidata, and Wikipedia. Dashboard **Refresh** imports TMDB's current U.S. theatrical movie list and next seven days of on-air TV listings, plus up to 250 Watchmode movies and 250 TV series available in the U.S. Watchmode movies are stored in Cinema Feeds and series in TV Networks under the **Streaming** subcategory. Selecting a streaming title retrieves provider links on demand; source and catalog responses expire after 30 days. Watchmode image URLs are not used. For music, Apple song and music-video previews are cached locally; the detail screen chooses a video preview first, otherwise an audio preview over the animated waveform. Preview playback starts muted and the sound control can unmute it when VLC is available. Long detail text wraps and grows with the window, while only long result cards expand. It no longer scrapes YouTube's search page. `main.py` uses trailer IDs supplied by TMDB when available; otherwise its YouTube search action opens a normal search page in the user's browser. Person biographies use Wikipedia.

### `events.py`

Loads and saves API settings, constructs ticket-vendor search URLs, parses Ticketmaster Discovery API results, categorizes music events, sports, festivals, and fairs, and saves those live listings into the local catalog. Its configuration file is `~/.spotlight/config.json`.

### `community.py`

Validates organizer event submissions, loads an optional hosted JSON feed, adds feed events to the catalog, and stores local submission state/cache files under `~/.spotlight`. It calls `database.py` and `events.py`.

### `promote.py`

Defines the in-app organizer submission form. It validates form data using `community.py`, stores a pending submission locally, and offers copy/save/email actions. A curator reviews and publishes events separately.

### `trailer_window.py`

Separate-process trailer display helper. `main.py` starts it for a YouTube video ID when `pywebview` is installed; otherwise the trailer opens in the system browser.

### `curator.py`

Command-line helper for validating, listing, adding, removing, and pruning entries in the public community feed JSON. It is not imported by `main.py`; it is used by whoever curates the shared feed.

## Active data and asset files

| Path | Purpose |
|---|---|
| `events.json` | Example/curated community feed file consumed by `curator.py` when run from this folder. The desktop app fetches a configured URL instead of reading this local file directly. |
| `%USERPROFILE%\.spotlight\media\posters` | Downloaded and cached title posters and event images. |
| `%USERPROFILE%\.spotlight\media\backdrops` | Downloaded backdrop images used in title detail views. |
| `%USERPROFILE%\.spotlight\media\people` | Downloaded person photos and cached biography JSON. |
| `%USERPROFILE%\.spotlight\media\videos` | Downloaded video previews and videos imported by the user. |
| `media/videos/` | Legacy location searched for existing local title videos; new videos are saved to the user-data folder. |
| `media/ambient/` | Optional category background videos. `main.py` falls back to generated visuals when a video is absent. |
| User-data media folders | Created by `main.py` if missing. Existing poster, backdrop, and people caches are copied there without overwriting newer files. |
| `media/LightWave_logo.png` | Logo loaded by the dashboard. |
| `media/Mythic Mask Works promotional banner2.png` | Branding image loaded by the dashboard. |
| `media/spotlight.ico` | Application icon. |

## Stored data outside the project

`database.py` creates `~/.spotlight/spotlight_storage_v2.db`. `events.py` writes its configuration to `~/.spotlight/config.json`. `community.py` stores submission and feed cache JSON files in the same folder. These files can contain personal account data or private organizer contact information and should not be committed.

`main.py` stores mutable UI/provider metadata in `%USERPROFILE%\.spotlight\spotlight_meta.json`. On first startup after this change, it copies the older project-root `spotlight_meta.json` there if no user-data copy exists; the original file is left in place as a local backup and is ignored by Git. The one-time demo-seed marker lives in this user-data metadata. Existing videos in project-local `media/videos/` remain in place to avoid copying large user files; the app still searches there, while new downloads and imports go to user data.

## Not part of the active app path

`Extra/` contains historical copies and supporting files. `Trailer Window Test 1/` contains a trailer-window test copy. Neither is imported by the top-level `main.py`. These are intentionally excluded from this current architecture map.
