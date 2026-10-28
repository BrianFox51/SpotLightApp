# Provider secret management (server groundwork)

Provider API keys are being moved from each desktop installation to the SpotLight server. During this interim phase, authorized operators manage them over SSH; the planned website portal will use the same server-side secret service later. The regular desktop app must not receive provider key values.

## What is managed

The encrypted version store currently supports `ticketmaster`, `tmdb`, `watchmode`, `igdb_client_id`, `igdb_client_secret`, `youtube`, `spotify_client_id`, and `spotify_client_secret`. YouTube and Spotify entries are placeholders and are not currently used by Spotlight.

Each change appends a version. History records the operator account, time, note, and a short SHA-256 fingerprint for distinguishing versions. A restore creates a new version from the selected encrypted historical value; it never edits or removes history. Clear appends a tombstone. The command line tool never prints the secret itself and prompts for new values without echoing them or placing them in shell history.

The database stores encrypted values. `PROVIDER_SECRETS_ENCRYPTION_KEY` is the separate Fernet key that protects them. Generate this once on the server with:

```sh
sudo docker compose exec api python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Put the generated value in the server's ignored `.env` file as `PROVIDER_SECRETS_ENCRYPTION_KEY=...`, protect the file with mode `600`, and recreate the API container. Store a secure backup of this encryption key separately from the database backup. If it is lost, encrypted provider keys and their historical versions cannot be recovered. Never commit or paste it into chat.

## Interim SSH commands

Run these from `~/SpotLightApp/server` on the server:

```sh
sudo docker compose exec api python -m app.provider_secrets_cli status
sudo docker compose exec api python -m app.provider_secrets_cli set tmdb
sudo docker compose exec api python -m app.provider_secrets_cli history tmdb
sudo docker compose exec api python -m app.provider_secrets_cli restore tmdb 1
sudo docker compose exec api python -m app.provider_secrets_cli clear tmdb
```

The `set`, `restore`, and `clear` commands ask for an active Spotlight admin username for audit attribution. `set` prompts for the provider value twice without echoing it. Do not append the key to the command itself. Provider key names are listed by `status` and accepted by the command parser.

## Scope and next steps

TMDB and Ticketmaster now use server-backed catalog paths. The server reads their encrypted keys, fetches provider data, and returns changed cards without returning key values. Ticketmaster refreshes are scoped to the selected state or the signed-in member's approximate local coordinates and are rate-limited. The desktop stores a cursor for each search area and applies returned cards to its existing SQLite cache, which remains available offline. During beta migration, local provider keys remain a fallback when the server cannot be reached. Guests continue to use the local path where configured and retain their own offline card cache. Watchmode and IGDB remain desktop-side until their server sync paths are added. Database, JWT-signing, SMTP, SSH, and other operational credentials remain in protected server configuration because changing them can affect boot, login, or recovery. A website portal will be added after its HTTPS hosting is available and will never return stored values to the browser.

A provider may revoke an old key. Restoring a historical version only restores the locally stored value; it cannot reverse provider-side revocation.
