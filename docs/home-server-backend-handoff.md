# Spotlight Home Server Backend Handoff

## Purpose

This document is an operating and follow-up guide for the optional online backend used by the Spotlight Windows desktop app. The app remains local-first for catalog data, API settings, and local profiles, while the server provides online accounts, editable profiles, favorites endpoints, moderated event submissions, and a member discussion board. The home server is intended to run the API and PostgreSQL; this guide describes safe maintenance and the remaining setup needed for email recovery.

The initial backend provides shared Spotlight accounts, editable profiles, cross-device favorites, and moderated community event submissions. Provider keys initially stayed in local settings; following an explicit design decision, TMDB and Ticketmaster now have incremental server-backed catalog paths using encrypted provider secrets. Remaining providers stay local until their individual server paths are implemented.

## Recommended first deployment

Start with a private test server reachable only from the owner's devices. Use a supported 64-bit Linux server or VM (for example, Debian or Ubuntu Server) with a static LAN address or DHCP reservation, at least 2 CPU cores, 4 GB RAM, SSD storage, and an external backup target. A small x86-64 or ARM64 machine is adequate for the API and PostgreSQL at beta scale. Linux is the recommended host because the service can run headlessly and be updated independently of the Windows desktop app.

Use this service layout:

```text
Spotlight desktop app
        │ HTTPS
        ▼
Reverse proxy / private access gateway
        │ private container network
        ├── FastAPI application
        └── PostgreSQL database
```

Use Docker Compose for the API and database. Keep PostgreSQL on a private Compose network with no public port. Bind the API to loopback or the private container network; the reverse proxy is the only network entry point. Do not expose the server's desktop, SSH, database, or Docker control socket to the internet.

For the first phase, use Tailscale Serve to reach the service only from devices in the owner's tailnet. When outside beta testers need access, choose and document a public HTTPS route, domain, and access policy before enabling it. A public tunnel only transports requests; it does not replace account authentication, rate limiting, or application security. Tailscale distinguishes private Serve from public Funnel; do not use a public Funnel URL for a service containing private account data without a separate security review.

## Backend stack and repository deliverables

Build a separate service, for example under `server/`, rather than importing desktop UI modules into it:

- Python 3.12 or newer, FastAPI, and Uvicorn.
- PostgreSQL for accounts, profiles, favorites, sessions, event submissions, moderation history, and audit records.
- SQLAlchemy 2.x and Alembic for persistence and versioned database migrations.
- Pydantic request and response schemas; OpenAPI docs available only on the private/test deployment unless intentionally enabled.
- Dockerfile and `compose.yaml` for the API, PostgreSQL, and optional reverse proxy.
- `.env.example` with placeholder values only; secrets must be provided at runtime and excluded from Git.
- A health endpoint, structured logs with secrets and personal data omitted, database backups, and a restore procedure.
- Backend API client and sync adapter in the desktop app, separated from Tkinter screen code.

Pin compatible dependency versions and use a lock file before the first shared beta. The backend should start with PostgreSQL, even for one home server, so account and event data have a clear server-owned source of truth and are not coupled to one desktop SQLite file.

## Features and API contract

Version the API from the beginning (`/api/v1`). Return predictable JSON errors, validate every request server-side, use UTC timestamps in storage, and provide a documented health check.

| Feature | Initial endpoints and expected behavior |
|---|---|
| Health | `GET /api/v1/health` reports API and database readiness without exposing secrets or internal configuration. |
| Accounts | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and session refresh/revoke endpoints. Login responses must not reveal whether an email or username exists. |
| Profile | `GET /api/v1/me` and `PATCH /api/v1/me` for full name, unique username, verified email, state, ZIP, optional bio/interests/site, and avatar reference. Keep private email and ZIP out of public profile responses. |
| Recovery | Username reminders are emailed to the account address. Password recovery uses a one-time 8-digit email code, stored as a keyed hash, expires after 15 minutes, allows limited attempts, and revokes active sessions when used. Both request endpoints return a generic response whether or not an account exists. SMTP must be configured in the server's private `.env`. |
| Favorites | `GET /api/v1/me/favorites`, `PUT /api/v1/me/favorites/{category}/{provider_id}`, and `DELETE` for the same key. Use stable catalog/provider IDs when available; do not depend on a display title alone. |
| Community submissions | Create a submission, list the signed-in user's submissions and statuses, and allow withdrawal while pending. Store owner account, server-assigned `submitted_at`, event date range, type, venue, public link, and moderation status. |
| Public community feed | `GET /api/v1/community/events` returns approved, non-expired listings with category/date filters and pagination. Never return contact email, reset data, or private account fields. |
| Moderation | Admin-only review, approve, reject, and removal actions with reviewer, timestamp, and reason recorded. Do not make a user submission public before approval. |
| Member Community | Authenticated members can create categorized discussions, reply, and report content; admins can review reports and hide or dismiss the reported content. This board is separate from the moderated event submission feed. |

### Event ordering policy

The server is authoritative for submission time; ignore any client-supplied `submitted_at`. Once approved, a registered user's listing should rank before third-party listings for the same event date. Among registered-user listings for that date, sort by the original server submission time, oldest first. Then sort third-party listings by event date and the existing relevance/date policy. Approval time must not change a listing's original place in the queue. Keep expired events out of the active feed, with a separate owner/admin path for favorited or archived records if needed.

Show this policy in the submission form before submit. The desktop app should label submission status clearly (for example, Draft, Pending review, Approved, Rejected) and distinguish user-submitted entries from provider-sourced listings.

## Security and privacy requirements

- Require HTTPS for every non-local connection. Never send passwords, access tokens, reset tokens, or profile data over plain HTTP.
- Hash passwords with Argon2id using a maintained library and current OWASP guidance. Do not reuse the local desktop password hash as the online authentication scheme without an explicit migration and password-reset plan.
- Use revocable, expiring sessions. Store a hash of opaque refresh/session tokens server-side; rotate refresh tokens. Do not put long-lived secrets in URLs or logs.
- Store server secrets in protected runtime configuration or an encrypted secrets manager, never in source control, image layers, or committed Compose files. Provider keys are an approved server-side feature: Spotlight keeps encrypted, append-only versions with admin-attributed audit records. Keep the encryption key backed up separately from the database. The desktop app must never receive provider secret values.
- Rate-limit login, registration, recovery, and event submission. Add account lockout/backoff, input length limits, and anti-automation controls appropriate to the beta.
- Restrict avatars to a small allowlist of raster image formats and size limits. Verify file contents, decode and re-encode the image, use random server filenames, and never serve user uploads as executable content.
- Use role-based authorization for every profile, favorite, submission, and moderation operation. A user must only modify their own data; admin actions must be auditable.
- Minimize personal data. Make display name, avatar, bio, and interests visibility choices explicit. ZIP, email, password, and recovery metadata must be private by default.
- Back up the database and uploaded images, encrypt backups, restrict access, and perform a restore rehearsal before inviting testers.

See the OWASP password guidance and FastAPI deployment guide in References. FastAPI's docs specifically cover proxy headers and container deployment; proxy trust must be limited to the actual proxy, not arbitrary clients.

## Connecting the Windows desktop app

Keep local-only use working when the server is unavailable or not configured. Add a small `backend_client.py` that owns HTTP requests, timeouts, JSON parsing, and authentication headers; do not issue network requests on Tkinter's UI thread. Route calls through the app's existing worker/UI queue pattern.

Add an explicit backend URL setting with a visible connection state. For the initial private test, use the server's private HTTPS name. Do not silently fall back from a failed online login to a different local account with the same username; make account mode clear to the user.

Suggested desktop integration order:

1. Add a read-only health/connection check and show Online, Offline, or Not configured.
2. Implement online account creation and sign-in while leaving guest/local mode available.
3. Add profile read/edit and remote favorites, with clear sync indicators and conflict rules.
4. Add event submission, user submission status, withdrawal, and approved feed retrieval.
5. Enable username/password recovery only after verified email delivery is configured and tested.
6. Add export/import tooling. Make imports opt-in and previewed; never upload the local SQLite database, API keys, remembered password, or private submission email automatically.

During migration, ask users to create or verify an online account. Do not transmit the current local password hash as a substitute for a verified registration. Allow users to export and selectively import favorites and profile fields after sign-in. Keep provider credentials in local Spotlight settings unless a future design explicitly moves a provider integration to the server and its terms have been reviewed.

## Build and run procedure

The following are the operator steps once the developer has added the service files; this repository does not currently contain the backend implementation or Compose deployment files.

1. Install a supported 64-bit Linux server, apply system updates, create a non-admin service account, enable the host firewall, and give the server a reserved LAN address.
2. Install Docker Engine and the Docker Compose plugin from the official instructions for that Linux distribution. Do not expose the Docker API socket.
3. Clone the approved Spotlight repository on the server. Review the source and confirm `.env`, database files, uploaded images, and backups are ignored by Git.
4. Copy `.env.example` to `.env`; set a unique database password, session-signing/sealing secret if used, allowed desktop origins/hosts, admin bootstrap method, and email delivery settings. Restrict file permissions. Never paste the values into chat or commit them.
5. Start the database and API on the private network first: `docker compose up -d --build`.
6. For schema changes, inspect the current Alembic revision before applying a migration. The API currently calls `Base.metadata.create_all` at startup, which creates missing tables; do not run a migration against the live database until its revision state is known.
7. Create the first admin account through a one-time local bootstrap command. Disable/remove that bootstrap path after use.
8. Configure HTTPS/private access. For owner-only tests, use Tailscale Serve and verify that a device outside the tailnet cannot reach the API. For invited testers, configure the chosen public gateway, domain, TLS, firewall, and rate limits; verify only intended API routes are reachable.
9. Set SMTP relay values in the private server `.env` (host, port, sender, and relay credentials if required), rebuild/restart the API, then test username reminder and password reset delivery with a non-production account. Never paste mail credentials into chat or commit them.
10. Point one development copy of Spotlight at the backend. Test signup, sign-in, profile privacy, recovery email, Community post/reply/report/moderation, favorites, submission moderation/order, logout/revocation, and offline behavior before enabling more clients.
11. Configure scheduled encrypted backups and log rotation. Perform a restore rehearsal to a separate test database. Record the tested recovery point and restore steps.

Routine operation:

```sh
docker compose ps
docker compose logs --since=30m api
docker compose pull
docker compose up -d --build
```

Run database migrations during a planned update before opening the app to users. Back up before migrations and keep the previous release available for rollback. Do not use `docker compose down -v` on the live host; that can delete persistent database data.

## Release gates before inviting other people

- Threat-model and review authentication, authorization, reset links, file upload, rate limiting, and reverse-proxy configuration.
- Verify HTTPS from a device outside the home network and confirm that no private server ports are reachable.
- Verify backups can actually be restored, and document who can access them.
- Confirm privacy notice, account deletion, email handling, avatar retention, event moderation, and data export behavior.
- Review provider and content licenses for every public feed. Keep attribution with provider-sourced listings.
- Test the server restart, router/internet outage, disk-full case, expired certificate, database restore, and client offline mode.
- Do not describe the community as public or enable recovery buttons until those flows reach the real backend and email service.

## References

- [FastAPI deployment in Docker](https://fastapi.tiangolo.com/deployment/docker/)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) for private tailnet access
- [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel) for public exposure; review its public-access behavior before use
- [Spotlight architecture](architecture.md)
- [Spotlight maintainer guide](maintainer-guide.md)

### Shared TMDB catalog

The authenticated `/api/v1/admin/catalog/tmdb/refresh` action is admin-only and rate-limited. It reads the encrypted TMDB key on the server, fetches the current U.S. movie and on-air TV pages over HTTPS, and persists only changed provider cards. Signed-in desktop clients request changes after their local cursor; the client stores the cursor only after its local SQLite write succeeds. The desktop cache remains the offline source. Provider failures are returned without logging or echoing the key.
