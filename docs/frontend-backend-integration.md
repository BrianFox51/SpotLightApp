# SpotLight Frontend–Backend Integration Notes

## Purpose

Connect the Windows desktop app to the optional SpotLight backend without breaking guest access, local sign-in, or favorites already saved on this computer.

Treat this as a working reference. Update it whenever an API field, data mapping, or connection flow changes.

## Current status

- The Windows development computer and Linux server are connected through the same Tailscale network.
- The API responds at `http://100.92.25.113:8001`.
- The health endpoint was confirmed working at `/api/v1/health`; it reported both status and database as healthy.
- The interactive API docs load at `/api/v1/docs`.
- The server container is published on `100.92.25.113:8001`, bound to the server’s Tailscale address.
- The desktop repository is clean and matches GitHub at commit `2fab35f` before adding the new client module.
- A new root-level `server_client.py` has been created and passed Python’s syntax compilation check. It is not yet connected to the UI.
- The server-specific Compose address is machine-specific. Keep that change on the server; don’t copy the Tailscale IP into the public application source.

## Existing desktop behavior — confirmed

- The Sign In tab uses a local username and password, checked by `database.verify_user`.
- Create Profile writes to the local SQLite database through `database.create_user`.
- Continue as guest opens the app without a server account.
- Local favorites are stored in SQLite under `(username, media_id)`. Guest favorites use the username key `__guest__`.
- A local `media_id` is a SHA-1 hash of category, title, and subtitle.
- The local `media_items` table has no dedicated `provider_id` column. It stores a `sources` value serialized from `item["srcs"]`; we have not confirmed whether that list contains provider IDs.

## Backend API contract — confirmed from the docs

The desktop client’s base URL must include the API prefix:

```text
http://100.92.25.113:8001/api/v1
```

| Operation | Method and path | Request | Success response |
|---|---|---|---|
| Register server account | `POST /auth/register` | `email`, `username`, `password` | `id`, `email`, `username`, `role` |
| Sign in | `POST /auth/login` | `email`, `password` | `access_token`, `refresh_token`, `token_type`, `expires_in` |
| Refresh session | `POST /auth/refresh` | `refresh_token` | New access and refresh tokens, token type, expiry |
| Revoke session | `POST /auth/revoke` | `refresh_token` | Revocation response |
| Load server profile | `GET /me` | Bearer access token | `id`, `email`, `username`, `role`, and profile fields |
| List server favorites | `GET /favorites` | Bearer access token | List of favorites |
| Add server favorite | `POST /favorites` | `category`, `provider_id`; bearer access token | Favorite with server `id`, `category`, `provider_id`, `created_at` |
| Remove server favorite | `DELETE /favorites/{favorite_id}` | Server favorite ID; bearer access token | HTTP 204 |

The profile response includes a nested profile with fields such as `full_name`, `state`, `zip`, `bio`, `interests`, `site`, and `avatar_ref`.

## Data mapping and preservation rules

- Keep local sign-in, local profiles, and guest access available when the server is offline.
- Add server sign-in as a separate option. Server sign-in uses email; local sign-in uses username.
- Do not automatically upload, delete, or merge existing local favorites.
- A local `media_id` is not the same as the server’s `favorite_id` or `provider_id`.
- The server identifies a favorite by category and provider ID. The local database currently stores its own hashed media ID.
- Before syncing favorites, confirm where stable provider IDs come from and persist that mapping. Until then, favorites remain local.
- Never treat a successful server sign-in as a successful favorite sync. They are separate operations.

## Token and connection handling

- Send the access token only in the HTTP `Authorization: Bearer ...` header for protected API calls.
- Send the refresh token only to refresh or revoke the server session.
- Do not print or paste tokens into chat, terminal logs, screenshots, or Git commits.
- Do not store a plaintext password for server sign-in.
- Before persisting a refresh token, protect it using the existing Windows DPAPI helper in `local_secrets.py`.
- Keep network calls off the Tkinter UI thread; update widgets through the app’s existing UI queue.
- Read the server URL from configuration or `SPOTLIGHT_API_BASE_URL`. Do not hardcode this machine’s Tailscale address into public source code.
- Keep the API private to the tailnet. Do not enable Tailscale Funnel.

## Integration sequence

1. Finish the API helper and review its diff.
2. Add a separate server-account sign-in/profile flow. Leave local and guest flows unchanged.
3. Verify server sign-in and profile retrieval from the Windows app; do not display or log tokens.
4. Add stable provider-ID storage to catalog items before implementing favorite sync.
5. Implement favorite loading, adding, and removal as separate operations, preserving local favorites.
6. At each checkpoint, inspect the changed files and Git status before committing and pushing.

## Items still to verify

- Whether `item["srcs"]` contains any stable provider identifiers.
- Which provider ID should identify a catalog item when several providers supply it.
- How server favorites should be matched to locally cached catalog items on another device.
- The exact server-account UI and how its session is restored after restarting the desktop app.