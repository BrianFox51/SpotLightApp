# SpotLight Frontend–Backend Integration Notes

## Purpose

Track the desktop app's integration with the optional SpotLight backend, including which behavior is implemented and which remains local or planned. Update this file whenever an API field, identity mapping, sign-in flow, or data ownership rule changes.

## Current status (2026-10-27)

- The desktop app can sign in to the optional SpotLight server using either an account username or email plus password.
- The client uses the home-beta API address by default. **Server connection settings** on the sign-in screen can save a different address for the current Windows account; a saved address takes priority over the development-only `SPOTLIGHT_API_BASE_URL` override. Addresses must include `/api/v1`.
- A successful server sign-in retrieves `GET /me` and holds access and refresh tokens in memory for the current app session.
- The desktop Create Profile tab now offers separate **Create online account** and **Create local profile** actions. Online creation calls `POST /auth/register`, signs in, and sends the entered profile fields to `PATCH /me` on a background worker. It then opens the dashboard with the server session active. Local creation continues to use SQLite and remains available offline.
- Server account passwords require at least 12 characters; local profiles continue to require at least 6. Choosing online creation does not silently fall back to local creation when the server is unavailable. Online profile photos are optimized to WebP and stored on the server at no more than 100 KB.
- The profile image on the dashboard opens the profile editor. Online profile fields and sharing preferences are saved with `PATCH /me`; account email and ZIP remain private. Members can choose whether to share their photo, state, bio, interests, or site. Name, role, and join date are always visible to signed-in community members.
- If registration succeeds but the follow-up sign-in or profile save fails, the app reports that the online account was created and directs the user to sign in; it does not pretend that local creation succeeded.
- A local profile can sign in on this PC without the server. After a successful online sign-in, the **Remember me** option can save a salted password verifier and limited profile snapshot in the local SQLite database for same-PC offline sign-in. This offline session has no server token and receives no online or administrator privileges. The cached verifier is not used when the server responds with an authentication rejection; a successful server password reset clears the offline snapshot. Guest access remains available.
- Favorites in the desktop app remain local SQLite records. The server client has favorites API methods, but the UI does not call them and no local-to-server favorite mapping or sync is implemented.
- The dashboard's six category count tiles open their matching category views, and the account-specific Favorites tile and in-app Favorites button open a dedicated Favorites list. Guest activation shows the registration prompt. Favorite items remain tied to the current local username.
- Server sign-out currently clears the desktop session; it does not call the API revoke endpoint. The refresh token is not persisted or used to restore a server session after restarting the app.
- Login recovery links use the online server when `SPOTLIGHT_API_BASE_URL` is configured: username reminders go to the account email, and password recovery uses a one-time 8-digit code that expires after 15 minutes. Local profile recovery remains available as a separate action and still requires its local verification fields. Online recovery requires SMTP settings on the server; without them, the server returns a configuration message and sends no email.
- The dashboard Community action opens a server-backed member discussion board for online accounts. Each discussion card has a direct **Reply** action that opens its thread and reply composer. New posts support bold, italic, underline, font family and size, plus up to four attached JPEG, PNG, or WebP photos. The server sanitizes rich-text markup and converts uploaded photos to WebP, limited to 600 KB each and 1600 pixels on the longest edge. Attachments are available to signed-in members in the thread view. Admins can review reports, hide posts or replies directly, and restore hidden content; every direct moderation action is written to the audit log. Hidden content is soft-hidden rather than permanently deleted. Local profiles and guests are prompted to sign in to an online account. This is a moderated member board, not a public event listing feed.
- Community and recovery API storage is added through SQLAlchemy models and a versioned Alembic migration. The current API startup also runs `Base.metadata.create_all`, so it creates missing tables automatically on startup; do not manually run the new migration against the existing server without first checking its Alembic revision state.

## Confirmed desktop behavior

### Sign-in and profile ownership

- `dashboard.Gate.do_login` checks local credentials and attempts server sign-in on a background thread.
- Server login sends `identifier` and `password` to `POST /auth/login`, then uses the returned access token for `GET /me`.
- On a successful server login, the desktop stores access and refresh tokens only in memory. When Remember me is enabled, Windows DPAPI protects the optional autofill password, and SQLite separately stores a salted verifier plus a limited profile for offline sign-in. No refresh token is saved to disk.
- Local profiles remain separate from online accounts and may sign in locally. For an online account, **Remember me** controls a same-PC offline credential snapshot; it stores a per-account salted verifier and a limited profile, not the server token or administrator role. The snapshot is used only if the server is unreachable, never when the server rejects the credentials. Unchecking Remember me removes the local offline verifier.
- **Create local profile** writes a profile to the local SQLite database and remains available offline.
- **Create online account** calls `POST /auth/register`, signs in, and updates the server profile with the entered name, state, ZIP, bio, interests, and site. These network calls run on a background worker. The app then opens the dashboard with server tokens held in memory for the session. A selected photo is uploaded and compressed to WebP, capped at 100 KB in server storage.
- Clicking the dashboard profile image opens the profile editor. For online accounts, editable profile fields and visibility preferences are sent to `PATCH /me`; email remains read-only and ZIP is never included on public profile cards. Members can share or hide each optional field. Online photos are stored on the server and can be removed from the editor.
- Online signup enforces the server's 12-character password minimum and username format. Local profile creation retains its 6-character minimum. Online signup failure never silently creates a local-only account.
- Guest mode has no account identity and cannot use the Favorites star; selecting it shows the registration prompt.
- Local-profile recovery uses the local database and requires that profile's email and ZIP code. Server-account recovery uses the server and email codes; successful server password recovery removes that account's offline verifier from this PC. Local and server passwords remain independent.

### Favorites

- `database.py` stores local favorites by `(username, media_id)` in SQLite.
- Local `media_id` is a SHA-1 hash of category, title, and subtitle. It is not the server's favorite ID or provider ID.
- `ServerClient` exposes profile update and list/add/remove favorites methods. The UI uses profile update during online account creation; favorites methods are not yet connected.
- Provider refresh cleanup now deletes only rows owned solely by that provider and not favorited by any local account. An empty keep-list is treated as inconclusive and never clears a provider's catalog. Favorited rows are retained as cached catalog entries, including when Watchmode's age-based expiry runs. Old streaming-category rows migrate their favorite links to the replacement movie/TV item IDs before the old rows are deleted.
- Generic `database.delete_item` still removes favorites for its media ID. Avoid using it for provider refresh cleanup; use the guarded prune helpers instead.
- The dashboard category count tiles open their matching Spotlight categories. The Favorites tile opens the dedicated per-user Favorites page; guests receive a registration prompt. The top Favorites shortcut is hidden on login and the Favorites view, and is shown in Spotlight after entering from the dashboard.

### Refresh and catalog counts

- Opening the dashboard after sign-in or guest entry renders saved counts, prunes expired dated event cards, then starts six background source jobs once for that session. Cached cards remain available during refresh. The jobs are data sources, not one job per category: TMDB, Ticketmaster events, Ohio schedules, Watchmode, IGDB, and TVmaze.
- Registered accounts default to their profile state (or their locally saved search-state choice) and can select any U.S. state. Selecting an area changes the visible event filter; press Refresh to fetch the newly selected area's events. Guests see **Local**; selecting its control shows “Create a profile to enjoy these features.” The guest local radius is about 100 miles.
- The first online guest refresh with no saved approximate location requests IP geolocation from GeoJS. Spotlight stores only rounded coordinates, city/region, and lookup time in its local configuration; it does not save the raw IP. The approximate location is reused for later refreshes and cached cards remain available offline. The UI discloses this use. IP geolocation is approximate and may reflect a VPN or network gateway rather than the user's physical location.
- Ticketmaster event rows are tagged with their state or local search area. Switching areas filters new tagged event rows without deleting them. Legacy OhioFestivals.net rows are recognized as Ohio-only and hidden outside Ohio. The Ohio-specific fair calendar runs only for Ohio searches; other states currently use Ticketmaster event results, and additional vetted local fair sources remain a follow-up.
- A refresh can report fewer than six successful updates because a source may be skipped when credentials or a state are unavailable. The summary distinguishes success, failure, and skipped jobs.
- `database.dashboard_stats` provides the cached catalog and per-user favorite counts. The dashboard uses the same expiry and area-filtered event cards as Spotlight for its music, sports, and festivals tiles; movie, TV, and game tiles show the saved catalog counts. The headline total is recomputed from those six displayed tiles. Refresh results are merged by stable local media ID, so repeated results update existing rows instead of incrementing counts for duplicates.
- Expired Ticketmaster and Ohio event cards are pruned on every dashboard entry, before dashboard counts are calculated. Favorited cards are retained. This date-based cleanup is separate from choosing a state or pressing Refresh. TVmaze and Ohio schedule refreshes also prune stale provider-only rows after non-empty results. Watchmode's bounded first page is inconclusive for missing rows; its 30-day age cleanup removes expired, un-favorited Watchmode-only rows at app startup.
- Ticketmaster does not delete cards merely because they are absent from one refresh response. Date-based cleanup removes past events; provider refresh cleanup retains favorites and shared-source cards. A failed or empty fetch does not trigger a clear-all.
- Signed-in accounts refresh Ticketmaster through the server for their selected state or profile coordinates. The server uses its encrypted key, stores scoped changed-card deltas, and returns event data without the key. Desktop cursors are stored per area and advance after SQLite saves; the existing local-key path remains a fallback during beta, and guests stay on the local path.
- Ticketmaster refresh requests are rate-limited. If a refresh was recent, the desktop still requests the latest shared delta rather than treating the rate limit as a failed catalog read.
- The admin-only **Clear card cache** action is available to a server-authenticated account whose server role is `admin`. It asks for confirmation, removes un-favorited catalog rows without personal notes and their linked event/credit rows, and resets the last-refresh marker. It keeps favorites, personal notes, accounts, API keys, source metadata, and image files. Afterward, Refresh repopulates immediately, or signing out and back in exercises the automatic dashboard refresh.
- Favorites counts are scoped to the current local username. They are separate from catalog totals and event counts; server favorites are not synchronized with local favorites.

## Confirmed backend API contract

| Operation | Method and path | Request | Success response |
|---|---|---|---|
| Refresh shared Ticketmaster events | `POST /catalog/ticketmaster/refresh` | Bearer access token; either `state_code` or `latitude`, `longitude`, and optional `radius` | Scoped changed-card cursor and counts |
| Read changed Ticketmaster events | `GET /catalog/ticketmaster?scope=...&since=...` | Bearer access token; area scope and local cursor | Scoped event card deltas |
| Refresh shared Watchmode catalog | `POST /admin/catalog/watchmode/refresh` | Admin bearer access token | Changed-card cursor and counts |
| Read changed Watchmode cards | `GET /catalog/watchmode?since=...` | Bearer access token; local cursor | Movie and TV card deltas |
| Load Watchmode availability | `GET /catalog/watchmode/{title_id}/sources` | Bearer access token; rate-limited | U.S. streaming service links |
| Refresh shared IGDB catalog | `POST /admin/catalog/igdb/refresh` | Admin bearer access token | Changed-card cursor and counts |
| Read changed IGDB cards | `GET /catalog/igdb?since=...` | Bearer access token; local cursor | Popular/upcoming games and genre/platform dictionaries |
| Register server account | `POST /auth/register` | `email`, `username`, `password` | Account fields |
| Sign in | `POST /auth/login` | `identifier` or `email`, plus `password` | Access and refresh tokens, type, expiry |
| Refresh session | `POST /auth/refresh` | `refresh_token` | New token pair |
| Revoke session | `POST /auth/revoke` | `refresh_token` | Revocation status |
| Load server profile | `GET /me` | Bearer access token | Account fields and nested profile |
| List server favorites | `GET /favorites` | Bearer access token | List of favorites |
| Add server favorite | `POST /favorites` | `category`, `provider_id`; bearer access token | Server favorite record |
| Remove server favorite | `DELETE /favorites/{favorite_id}` | Bearer access token | HTTP 204 |
| Request username reminder | `POST /auth/recovery/username` | Account email | Generic accepted response; matching account username is emailed |
| Request password reset code | `POST /auth/recovery/password` | Account email | Generic accepted response; matching account receives an 8-digit, 15-minute code |
| Complete password reset | `POST /auth/recovery/password/complete` | Email, reset code, new 12+ character password | Password changed; existing sessions revoked |
| List Community discussions | `GET /community/posts` | Bearer token; optional category and pagination | Member-visible posts and reply counts |
| Create Community discussion | `POST /community/posts` | Bearer token; category, title, body | Created post |
| List Community post photos | `GET /community/posts/{post_id}/images` | Bearer token | Visible photo IDs and media types |
| Attach Community post photo | `POST /community/posts/{post_id}/images` | Author/admin bearer token; multipart image up to 4 MB | Server-optimized WebP attachment, max four per post |
| Read Community post photo | `GET /community/posts/{post_id}/images/{image_id}` | Bearer token | Private WebP image bytes |
| List or create replies | `GET/POST /community/posts/{post_id}/replies` | Bearer token; reply body for POST | Visible replies or created reply |
| Report Community content | `POST /community/reports` | Bearer token; post/reply ID and reason | Accepted report |
| Review Community reports | `GET /admin/community/reports` | Admin bearer token | Pending reports and content preview |
| Moderate Community report | `POST /admin/community/reports/{report_id}/moderation` | Admin bearer token; `hide` or `dismiss` | Recorded moderation action |
| Hide or restore post/reply | `POST /admin/community/content/{post\|reply}/{id}/moderation` | Admin bearer token; `hide` or `restore`, optional reason | Soft-hide state plus audit entry |
| List hidden Community content | `GET /admin/community/hidden` | Admin bearer token | Hidden posts and replies for restoration |
| Public member profile | `GET /profiles/{username}` | Signed-in bearer token | Name, role, and join date plus opted-in fields |
| Upload/remove profile photo | `POST/DELETE /me/avatar` | Signed-in bearer token; JPEG/PNG/WebP upload up to 4 MB | Server-optimized WebP, at most 100 KB |
| Public member photo | `GET /profiles/{username}/avatar` | Signed-in bearer token; member opted in | Optimized image bytes |

The profile response includes fields such as `full_name`, `state`, `zip`, `bio`, `interests`, `site`, and `avatar_ref`.

## Data mapping and preservation rules

- Keep guest access and local account access available when the optional server is offline.
- Do not automatically upload, delete, or merge existing local favorites.
- A local `media_id` is not interchangeable with a server `favorite_id` or provider `provider_id`.
- Before syncing favorites, identify and persist a stable provider ID for each catalog item, including how to handle items represented by multiple providers.
- Do not delete a user's favorite just because a provider temporarily failed or omitted a result. Provider refresh paths call prune only after successful data retrieval; guarded pruning keeps favorites and rows shared by multiple sources. Favorited stale entries currently remain in the local catalog because the UI does not yet have a separate stale-favorite presentation.
- Keep network calls off Tkinter's UI thread; update widgets through the app's UI queue.
- Do not print or paste access tokens, refresh tokens, passwords, API keys, or private account data into chat, screenshots, terminal logs, or Git commits.
- Keep the API private to the tailnet. Do not enable Tailscale Funnel.

## Next implementation priorities

1. Configure SMTP in the server's private `.env`, deploy the server changes, and verify delivery for username reminders and password reset codes using a non-production account. Never share SMTP credentials in chat or commit them.
2. Try the Community board with an online standard account and verify create, reply, report, and admin hide/dismiss flows. Keep the board for trusted beta accounts until moderation and abuse handling have been reviewed.
3. Verify dashboard category counts against visible cards after refresh, including provider merges, area filters, and expired-event pruning; the category tiles currently count the local catalog, while the saved-event tile is state-specific.
4. Verify guest IP location success, denial, unavailable-network fallback, and offline cached-card display; verify that choosing a member state only takes effect after Refresh.
5. Separately plan token refresh/revocation and server favorite synchronization. Do not imply those features are live until the desktop UI uses them.

## Items still to verify

- Whether category totals match distinct cards visible in each category after filtering, pagination, expired-event hiding, and provider merges.
- Whether dashboard category tile hover feedback is sufficiently visible across supported display scaling settings.
- Whether provider IDs are available in `item["srcs"]` or another stable field and which ID to use when multiple sources supply an item.
- Whether sign-out should revoke the current server refresh token and how errors should be handled.
- A safe definition of stale catalog data that preserves user favorites and does not treat temporary provider outages as successful empty results.
- The desired state-search choices and whether “Titles in [state]” should count catalog titles or upcoming events.
