# SpotLight Frontend–Backend Integration Notes

## Purpose

Track the desktop app's integration with the optional SpotLight backend, including which behavior is implemented and which remains local or planned. Update this file whenever an API field, identity mapping, sign-in flow, or data ownership rule changes.

## Current status (2026-10-17)

- The desktop app can sign in to the optional SpotLight server using either an account username or email plus password.
- The client reads its API base URL from `SPOTLIGHT_API_BASE_URL`; it must include `/api/v1`. Keep any personal Tailscale address in local configuration, not public source.
- A successful server sign-in retrieves `GET /me` and holds access and refresh tokens in memory for the current app session.
- Server account creation is not connected to the desktop Create Profile form. That form still creates a local SQLite profile.
- If server sign-in fails but the same credentials match a local account, the app falls back to local sign-in. Guest access remains available.
- Favorites in the desktop app remain local SQLite records. The server client has favorites API methods, but the UI does not call them and no local-to-server favorite mapping or sync is implemented.
- Server sign-out currently clears the desktop session; it does not call the API revoke endpoint. The refresh token is not persisted or used to restore a server session after restarting the app.
- Login recovery links open local account recovery dialogs. They operate on profiles stored on this PC and do not recover or reset server credentials.
- The Git working tree was clean at `aa0205f` when these notes were reviewed.

## Confirmed desktop behavior

### Sign-in and profile ownership

- `dashboard.Gate.do_login` checks local credentials and attempts server sign-in on a background thread.
- Server login sends `identifier` and `password` to `POST /auth/login`, then uses the returned access token for `GET /me`.
- On a successful server login, the desktop stores the access and refresh tokens only in memory. The optional Remember password setting stores the entered password using Windows DPAPI for the current Windows user; it does not persist the refresh token.
- A local profile is used if server access is unavailable or rejects the account and local verification succeeds. The status message distinguishes local fallback from server sign-in.
- The Create Profile flow writes a profile to the local SQLite database. It does not call `POST /auth/register`.
- Guest mode has no account identity and cannot use the Favorites star; selecting it shows the registration prompt.
- Username and password recovery use the local database and require the local profile's email and ZIP code. Password reset changes only the local profile password.

### Favorites

- `database.py` stores local favorites by `(username, media_id)` in SQLite.
- Local `media_id` is a SHA-1 hash of category, title, and subtitle. It is not the server's favorite ID or provider ID.
- `ServerClient` exposes list/add/remove favorites methods, but the desktop UI does not currently call them.
- Deleting a catalog row through the existing prune/delete helpers also deletes associated local favorites. Any automatic cache cleanup must account for this so a stale provider result does not silently erase a user's saved favorite.
- There is not yet a dedicated Favorites page. The dashboard Favorites count is informational; dashboard statistic cards are not yet interactive quick links.

### Refresh and catalog counts

- The dashboard's combined Refresh button starts six provider/event sync jobs. Refresh is user-triggered; the dashboard does not automatically refresh when it opens.
- The current search-area selector offers only the account's own state (or a disabled prompt when no state is available). Choosing another state and then refreshing is not implemented.
- `database.dashboard_stats` counts saved rows in `media_items` by category. Its headline `total` sums only the six categories displayed on the dashboard (`music`, `movies`, `tv`, `games`, `sports`, and `festivals`), so it equals the sum of those category tiles. These are saved catalog rows; event visibility rules can hide expired music, sports, or festival cards without deleting their cached rows.
- The state tile counts distinct catalog media IDs linked to saved event records whose location text contains the account's state code. Its label is “Items with saved events in [state]”; it does not claim to count all titles available in that state.
- `dashboard_stats` counts saved local event rows separately. It does not currently filter expired events from this saved-row count.
- The Favorites count is scoped to the current local username. It is independent of catalog totals and event counts.
- Refresh completion records a general `last_refresh_at` timestamp after the scheduled jobs finish. A timestamp alone does not establish that each provider succeeded; provider status is tracked separately.
- Some provider syncs prune records that disappear from a successful result. Watchmode rows also have an age-based prune. Review each source's success and expiry rules before adding automatic pruning.
- Past event cards are hidden by visibility checks, while that behavior is separate from deleting their database rows.

## Confirmed backend API contract

| Operation | Method and path | Request | Success response |
|---|---|---|---|
| Register server account | `POST /auth/register` | `email`, `username`, `password` | Account fields |
| Sign in | `POST /auth/login` | `identifier` or `email`, plus `password` | Access and refresh tokens, type, expiry |
| Refresh session | `POST /auth/refresh` | `refresh_token` | New token pair |
| Revoke session | `POST /auth/revoke` | `refresh_token` | Revocation status |
| Load server profile | `GET /me` | Bearer access token | Account fields and nested profile |
| List server favorites | `GET /favorites` | Bearer access token | List of favorites |
| Add server favorite | `POST /favorites` | `category`, `provider_id`; bearer access token | Server favorite record |
| Remove server favorite | `DELETE /favorites/{favorite_id}` | Bearer access token | HTTP 204 |

The profile response includes fields such as `full_name`, `state`, `zip`, `bio`, `interests`, `site`, and `avatar_ref`.

## Data mapping and preservation rules

- Keep guest access and local account access available when the optional server is offline.
- Do not automatically upload, delete, or merge existing local favorites.
- A local `media_id` is not interchangeable with a server `favorite_id` or provider `provider_id`.
- Before syncing favorites, identify and persist a stable provider ID for each catalog item, including how to handle items represented by multiple providers.
- Do not delete a user's favorite just because a provider temporarily failed or omitted a result. Prune only after a successful, appropriately scoped refresh and preserve the favorite reference or provide an explicit stale-favorite state.
- Keep network calls off Tkinter's UI thread; update widgets through the app's UI queue.
- Do not print or paste access tokens, refresh tokens, passwords, API keys, or private account data into chat, screenshots, terminal logs, or Git commits.
- Keep the API private to the tailnet. Do not enable Tailscale Funnel.

## Recommended next work

1. Audit the dashboard count definitions against the records and cards actually shown. Decide whether the state-specific tile counts titles or events, then align its label, query, and documentation.
2. Define source/category identity, refresh success criteria, and expiry rules. Verify that provider failures do not prune valid cached items or favorites.
3. Make the dashboard statistic cards intentional quick links, with visible hover/focus feedback and destinations mapped to the existing category/event views.
4. Build one dedicated Favorites page and make both dashboard and in-app navigation open that same page. Keep the guest registration prompt and local favorites behavior explicit until server sync is designed.
5. Add automatic refresh on dashboard entry only after the count/cache audit. Preserve usable cached results when offline or a provider fails; require an explicit refresh after changing the search area.
6. Separately plan server registration, token refresh/revocation, and favorite synchronization. Do not imply those features are live until the desktop UI uses them.

## Items still to verify

- Whether category totals match distinct cards visible in each category after filtering, pagination, expired-event hiding, and provider merges.
- Whether provider IDs are available in `item["srcs"]` or another stable field and which ID to use when multiple sources supply an item.
- Whether sign-out should revoke the current server refresh token and how errors should be handled.
- A safe definition of stale catalog data that preserves user favorites and does not treat temporary provider outages as successful empty results.
- The desired state-search choices and whether “Titles in [state]” should count catalog titles or upcoming events.
