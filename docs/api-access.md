# Provider access and integration notes

This document records how the current app accesses external information and what access is needed. Provider terms and requirements can change; check the linked official documentation again before release.

## YouTube

### Current behavior

- `main.py`'s **Find on YouTube** action opens a normal YouTube search in the user's browser. It does not need an API key.
- The former `online.py` search-page parser has been removed because it scraped YouTube's search-results HTML. YouTube's developer policies prohibit scraping YouTube applications or using scraped YouTube data.
- TMDB can provide a YouTube video ID in title metadata; playback is opened through `trailer_window.py` (when `pywebview` is installed) or the browser.
- As implemented, YouTube does not require a SpotLightApp API key: people can search directly on YouTube, and movie/TV trailer IDs can come from TMDB. A future feature that automatically searches YouTube through the Data API would require a Google Cloud API key and policy-compliant handling.

### Official API route

If a future version needs automated public video search, create a Google Cloud project, enable YouTube Data API v3, and create an API key. Search results use `search.list`; quotas are applied and visible in Google Cloud Console. Quota allocation and method costs can change, so use the live quota page rather than relying on a hard-coded estimate. An API key is enough for public search. OAuth is only needed for operations involving private user data or actions on a user's behalf.

The API does not grant permission to download or locally rehost YouTube videos. Continue to let YouTube/browser/player handle playback. A public YouTube API client also has policy requirements around clear source branding, terms and privacy notices, security, data retention, and keeping installed clients updateable. Review the full policy before adding API-backed features or distributing them.

### Credential handling

This API does not currently exist in SpotLightApp. An API key embedded in a Python desktop application can be extracted. Keep it in the user's local configuration during development, restrict it in Google Cloud where possible, and never publish it in source control. For a public desktop release, do not assume a shared key can be kept secret; decide between user-supplied keys and a service you operate, then review YouTube's policy for that design. Adding YouTube API access also brings user-facing terms, privacy, branding, security, and data-handling requirements that must be addressed before release.

Official references:

- [YouTube Data API getting started](https://developers.google.com/youtube/v3/getting-started)
- [YouTube API credentials](https://developers.google.com/youtube/registering_an_application)
- [YouTube API developer policies](https://developers.google.com/youtube/terms/developer-policies)
- [YouTube quota and compliance audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)

## IMDb

### Current behavior

The app does not currently call IMDb. Do not add IMDb website scraping as a shortcut.

### Official options

IMDb makes limited downloadable datasets available for personal, non-commercial use with specific restrictions, required acknowledgment, and the possibility that permission may be withdrawn. IMDb says this data may not be republished or repurposed to create an online/offline movie database except for an individual's personal use. A public SpotLightApp release should therefore not bundle or redistribute the non-commercial IMDb datasets. IMDb also offers licensed data products/API access through AWS Data Exchange. If IMDb data is essential to the public app, contact IMDb about an appropriate license and its current price before implementing it.

The current movie/TV provider is TMDB, not IMDb. For the stated public, free, no-revenue direction, TMDB's developer API is the practical route to investigate; its API is free for non-commercial use with attribution, while commercial use requires a commercial license. The current attribution notice is already shown in the movie/TV detail UI, but release readiness still requires following TMDB's full current branding/attribution requirements and checking that the project's actual distribution model qualifies as non-commercial.

Official references:

- [IMDb data/API documentation](https://data.imdb.com/documentation)
- [IMDb non-commercial datasets](https://www.imdb.com/interfaces/)
- [IMDb rules for using data in software](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX)
- [TMDB API FAQ and attribution](https://developer.themoviedb.org/docs/faq)
- [TMDB API getting started](https://developer.themoviedb.org/v4/docs/getting-started)

## Ticketmaster

### Current behavior

`events.py` already uses the Ticketmaster Discovery API v2. It expects `ticketmaster_key` in `~/.spotlight/config.json`, sends it as the `apikey` query parameter, and searches around the signed-in user's ZIP-derived latitude/longitude. Event sync also spaces calls to stay under the documented rate limit.

### Access steps

Register in the [Ticketmaster Developer Portal](https://developer.ticketmaster.com/), create an application, and use its Consumer Key as the API key. The Discovery API is available after registration. Ticketmaster currently documents a default public quota of 5,000 calls per day and 2 requests per second; check the account dashboard for the quota assigned to your application. The Partner API, which supports ticket purchase/transactions, is typically restricted to select Ticketmaster partners. SpotLightApp currently links out to ticket vendors; it does not purchase tickets. The affiliate program requires approval and can pay commission on attributed sales under its current terms.

### Credential handling

Keep the key in `~/.spotlight/config.json`, never in project source, screenshots, logs, or a committed sample containing a real key. A publicly distributed desktop app cannot keep a shared embedded key secret. For public release, choose user-provided keys or an approved server-side design and verify Ticketmaster terms, branding, and data-display requirements.

Official references:

- [Ticketmaster Discovery API v2](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/)
- [Ticketmaster getting started and rate limits](https://developer.ticketmaster.com/products-and-docs/apis/getting-started/)
- [Ticketmaster Partner API access](https://developer.ticketmaster.com/products-and-docs/apis/partner/)

## Watchmode

### Current status

For signed-in users, **Refresh** uses the shared Watchmode catalog maintained by a Spotlight admin. It contains a bounded first page of U.S. movies and TV series available through subscription, free, rental, or purchase services. Guests use the local Watchmode key if configured. Watchmode movies appear in Cinema Feeds and series in TV Networks, each under a dedicated **Streaming** subcategory. Opening a title loads its U.S. service links through the server for signed-in users, or directly with a local key for guest/offline fallback.

The catalog request loads up to 250 movies and 250 TV series (two list-page credits per refresh). Opening a title requests its U.S. service links on demand (one additional credit) and reuses the cached result for up to 30 days. Users can browse the cached catalog 25 items at a time. Watchmode artwork URLs are not used; the app uses its own generated artwork. Service links open the provider's own page when Watchmode supplies a URL.

### Planned use and access

Watchmode's API supports movie/TV title search, paginated title lists, and per-title streaming sources. The free Developer plan is explicitly non-commercial and has a monthly credit allowance and country limits. The API can return subscription, free, rental, and purchase availability; detail/source requests consume credits, so the integration uses bounded pages, local caching, and on-demand source lookups rather than loading the full catalog repeatedly.

Use the key only for the current non-commercial beta. Before monetization or a public release under a different model, recheck Watchmode's live plan terms and obtain the appropriate license. The signed-in beta uses an admin-managed server key; do not copy that key into the desktop app. A local key remains an optional guest and offline fallback.

Official references:

- [Watchmode API documentation](https://api.watchmode.com/docs)
- [Watchmode plans and credits](https://api.watchmode.com/)
- [Watchmode API terms](https://api.watchmode.com/tc)

## Other active sources

- Apple Search/iTunes endpoints and Steam store endpoints are used by `online.py` for product metadata, artwork, preview clips, and purchase links. Music previews use a matching music-video preview when available; otherwise a song preview plays over the waveform. These are previews, not full-track playback. The app caches preview media in the user's `%USERPROFILE%\\.spotlight\\media\\videos` folder. Starting muted and changing the sound requires VLC playback support from `requirements-optional.txt` plus the VLC desktop application.
- The dashboard's **Refresh** action uses shared server catalogs for signed-in accounts and retains local fallback where configured. Admins refresh TMDB, Ticketmaster, Watchmode, and IGDB; other members read shared card deltas. The server reads encrypted provider keys and returns catalog data without exposing key values. Ticketmaster searches the selected state or member's profile coordinates. Watchmode availability is loaded per title through the server and cached on the desktop for up to 30 days. Local SQLite remains available offline; guests use their separate local cache and local provider path.
- Wikipedia/Wikidata are used for biographies, article summaries, and fallback credits.
- ZIP-to-location lookup uses Zippopotam.us. The startup connection indicator checks Google connectivity.
- The community feed is a user-configured JSON URL; the curator tool can write `events.json` for hosting, such as from a GitHub raw-content URL.

These integrations need their own source attribution, caching, terms, and error-handling review before publishing.

## Local setup file

The Windows beta may still store Ticketmaster, TMDB, Watchmode, and IGDB/Twitch credentials in `%USERPROFILE%\.spotlight\config.json` as transitional fallbacks. Signed-in TMDB, Ticketmaster, Watchmode, and IGDB catalog paths use server-managed encrypted provider secrets first; key values and short-lived Twitch access tokens are never returned to the desktop. Watchmode per-title availability also uses the server when signed in. Guests retain local provider credentials and their own offline cache. See `docs/provider-secret-management.md` for SSH management. Spotify and YouTube are placeholders and are not wired into app behavior. Apple Search, Steam Store, Wikipedia, and Wikidata currently do not need user-supplied keys. A committed template may show key names only, never real credentials.
