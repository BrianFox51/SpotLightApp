# SpotLightApp

SpotLightApp is a Windows desktop media and local-events browser. It keeps a local catalog of music, movies, TV, games, sports, and festivals, then enriches that catalog with online details and nearby events.

This README describes the current application. It is a starting point for improving and documenting the program; it does not claim that every current integration is ready for public distribution.

## Start here

- [`main.py`](main.py) starts the desktop app and connects its screens and integrations.
- [`database.py`](database.py) stores the local catalog, user accounts, notes, credits, and event dates in SQLite.
- [`online.py`](online.py) retrieves media details and artwork from online sources.
- [`events.py`](events.py) retrieves nearby listings from Ticketmaster and builds ticket-search links.
- [`dashboard.py`](dashboard.py), [`community.py`](community.py), and [`promote.py`](promote.py) provide the sign-in/dashboard and community-event features.
- [`docs/architecture.md`](docs/architecture.md) explains the program flow and each active project file.
- [`docs/api-access.md`](docs/api-access.md) explains the current data providers, credential setup, and distribution considerations.
- [`docs/maintainer-guide.md`](docs/maintainer-guide.md) records the current data locations and a safe order for future changes.
- [`docs/asset-inventory.md`](docs/asset-inventory.md) records which visual assets are intended for public distribution and their known source.

## Requirements

Python's built-in Tkinter and the packages in [`requirements.txt`](requirements.txt) are needed for the main interface. Install them from the project folder with:

```powershell
py -m pip install -r requirements.txt
```

Optional video features are listed in [`requirements-optional.txt`](requirements-optional.txt). VLC playback also requires the VLC desktop application; trailer-window playback uses `pywebview` when installed and otherwise opens the browser. Package versions are not pinned yet; we’ll set and verify them as part of the clean-install review.

## Run

From the project folder, run:

```powershell
python main.py
```

The program initializes its SQLite database and user-data folders on startup. Downloaded posters, backdrops, cast photos, video previews, and imported local videos are stored under `%USERPROFILE%\.spotlight\media`. Existing image caches are copied there on first launch; existing local videos stay in the project folder and remain available. See the data-location notes in [`docs/maintainer-guide.md`](docs/maintainer-guide.md).

## Current limitations

- The automatic YouTube search-results parser has been removed because it scraped YouTube's website. The app can still open a user-initiated YouTube search in the browser and can use trailer IDs returned by TMDB. Neither path requires a YouTube API key.
- Movie and TV details can use TMDB when a key is configured. Other metadata/artwork lookups use Apple, Steam, and Wikipedia endpoints.
- IMDb is not currently an integration. IMDb offers limited official datasets for personal, non-commercial use and licensed API/data products; IMDb website scraping is not an appropriate substitute.
- Ticketmaster event sync already exists and expects a developer key in the local SpotLight configuration file.
- The local Git repository now exists, but no GitHub remote is connected yet. Automated tests, a dependency lock file, and a packaging recipe have not been added.

## Before publishing

Review provider terms and attribution, move writable caches and user data out of the installed project folder, document dependencies and setup, and verify that no credentials or private user data are included in the repository. The notes in `docs/` are an initial handoff, not a claim of provider approval or a release certification.

## License and reuse

No open-source license is included. The project is shared for viewing on GitHub; broader reuse permissions remain with the copyright holder. Contact the owner before reusing or redistributing the code or assets outside the permissions GitHub provides for viewing and forking a public repository.
