# Maintainer guide

## Safe first review

1. Read `docs/architecture.md` before changing application behavior.
2. Read `docs/api-access.md` before changing a provider integration or adding a credential.
3. Keep provider keys and personal records outside the project folder.
4. Preserve the local SQLite data unless a migration has been planned and backed up.
5. Keep the desktop UI responsive: network calls should not block Tkinter's main event loop.
6. When a provider lookup fails, preserve offline catalog use and report a useful, non-secret error.
7. Check `docs/asset-inventory.md` before adding visual files to a public commit.

## Current persistent data

| Data | Current location | Notes |
|---|---|---|
| SQLite catalog and user accounts | `%USERPROFILE%\.spotlight\spotlight_storage_v2.db` | Includes usernames, salted password hashes, saved titles, notes, cast/crew, and events. Back up before schema changes. |
| API/feed settings | `%USERPROFILE%\.spotlight\config.json` | May hold Ticketmaster and TMDB keys, plus community feed settings. Never commit this file. |
| User submissions | `%USERPROFILE%\.spotlight\my_submissions.json` | Can include an organizer's private contact email. Never publish it. |
| Community cache | `%USERPROFILE%\.spotlight\community_feed.json` | Local sync state. |
| UI metadata | `%USERPROFILE%\.spotlight\spotlight_meta.json` | The first startup copies the older project-root file here if needed; the old file remains as a local backup and is ignored by Git. |
| Downloaded image cache and new video files | `%USERPROFILE%\.spotlight\media` | Existing poster, backdrop, and people-photo folders are copied there without overwriting newer files. Existing videos remain in the project folder and are still searched; new previews and imports use the user-data folder. |

## Readability and handoff direction

Keep behavior stable while making the code easier to review:

- Replace dense one-line statements and abbreviated names with descriptive names in small, reviewable changes.
- Add module, class, and function docstrings that explain purpose, inputs, outputs, side effects, and failure behavior.
- Add comments for decisions and provider constraints, rather than restating each line of code.
- Separate UI construction, domain operations, provider clients, storage, and configuration as the code is understood.
- Document migrations and data ownership before moving or renaming persisted fields.
- Keep comments accurate as implementation changes; avoid promises such as "offline safe" unless the behavior has been verified.

## Event discovery direction

The intended experience should let each user choose a search scope rather than treating a larger radius as the only way to expand discovery:

1. **Near me** — nearby events centered on the user's saved location.
2. **Entire state or province** — a direct administrative-area search, such as all of Ohio, even when the user starts in Cleveland.
3. **Nearby states or provinces** — a regional view for people willing to travel.
4. **Country-wide** — all matching events in the selected country.
5. **Tour dates** — all dates for a selected artist or act, ordered by date or distance.

The current event sync offers a nearby search within a 75-mile radius and an entire-state search for U.S. accounts. Upcoming Ticketmaster music listings populate the Concerts & Music section. Music filters include Ticketmaster genres and the Bands & Live Shows and Music Festivals event types; filters with no saved matches are hidden. Spotlight Search is available across the main app and searches saved catalog data either everywhere or within the current category. It matches title, artist, venue, description, year, and saved genre/event-type metadata; it does not issue live provider requests as the user types. Search results and category feeds render 25 cards at a time with previous/next controls to keep large lists responsive. Sports, other festivals, and fairs populate their own sections. State-wide queries are limited to the first 1,000 matches per Ticketmaster query by the provider's deep-paging limit. Calls pause for 0.5 seconds between requests to stay at or below Ticketmaster's currently documented public limit of 2 requests per second; verify the quota assigned to the application in its developer account. The current ZIP lookup is U.S.-specific. Ticketmaster's Discovery API supports state and country filters in addition to location radius, so a state-wide search uses those provider filters rather than approximating a state boundary with a large circle. Keep provider/API results separate from user-specific location preferences so one local account's searches do not become another account's "near me" results.

For a later international version, collect a country along with the postal code and use a location lookup that understands the selected country's postal-code format. Keep distance units and event time zones explicit.

## Suggested order of work

1. Establish a clean baseline and identify which project files are intended for source control.
2. The YouTube search-results scraper has been removed. Keep the user-initiated browser search and TMDB-supplied trailer IDs unless a reviewed, policy-compliant API design is added.
3. Add regional, country-wide, and dedicated artist tour-date search scopes using supported provider filters.
4. Add clear local setup and credential validation for the APIs the owner chooses to use.
5. Move mutable metadata and downloaded cache files to a user-data directory with a migration that preserves existing data.
6. Refactor `main.py` into smaller, clearly named components without changing behavior, documenting each step.
7. Add dependency/version and Windows packaging instructions, then verify from a clean copy before release.
8. Review provider policies, attribution, and GitHub contents before publishing.

Do not publish until the owner has reviewed generated files, local data handling, provider terms, and whether the chosen API licenses permit the intended distribution and business model.
