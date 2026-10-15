# Visual asset inventory

This file records which visual assets are intended for a public source repository and what is known about their origin. Confirmed owner-created assets may be included. Do not add downloaded posters, cast photos, backdrops, trailers, or other third-party media to the public repository without checking the applicable rights and provider terms.

| File | Purpose | Known source | Public status |
|---|---|---|---|
| `media/LightWave_logo.png` | SpotLight logo used on the sign-in and dashboard screens. | Project owner says they created it. | Cleared by owner for publication. |
| `media/Mythic Mask Works promotional banner2.png` | Business banner shown on the sign-in screen. | Project owner says they created it. | Cleared by owner for publication. |
| `media/spotlight.ico` | Windows application icon. | Project owner says they created it. | Cleared by owner for publication. |
| `media/tmdb/tmdb_footer.png` | TMDB wordmark at the bottom of the sign-in page. | Supplied by project owner as a transparent PNG; matching original SVG is retained. | Used in the app; displayed without changing its colors or proportions. |
| `media/tmdb/tmdb_cinema.png` | TMDB logo under the SpotLight wordmark in Cinema Feeds. | Supplied by project owner as a transparent PNG; matching original SVG is retained. | Used in the app; displayed without changing its colors or proportions. |
| `media/tmdb/tmdb_detail.png` | TMDB logo above Notes for movie and TV details. | Supplied by project owner as a transparent PNG; matching original SVG is retained. | Used in the app; displayed without changing its colors or proportions. |

Downloaded image caches, local video files, and ambient videos are excluded from Git by `.gitignore`. The app stores new downloaded and imported files under the user's `.spotlight` data folder.
