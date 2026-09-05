# morning-coffee
A Test of AI capabilities, want to make a "morning coffee" app that gives me the info I want to start the day.

A small [Kivy](https://kivy.org) desktop dashboard, managed with [uv](https://docs.astral.sh/uv/),
that on launch shows three panels:

- **News** — a tabbed panel that aggregates news sources; switch between them with
  the tab row. Built-in sources: [Tiny Tiny RSS](https://tt-rss.org) (mark a story
  read with its checkmark button or clear the feed with "Mark all read", both writing
  back to the server) and [Lemmy](https://join-lemmy.org) (anonymous top-of-day posts,
  no login needed).
- **Mastodon** — a tabbed panel with your Notifications, Home timeline, Trending
  posts, and a Compose tab to publish a new post.
- **Weather** — a 7-day forecast for your location, by postal code (no API key needed).

The app is organized around pluggable **integrations** — adding a new data source
is a single new module (see [Adding an integration](#adding-an-integration)).

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.13 is provisioned automatically.

```bash
uv sync
```

This creates `.venv/`, writes `uv.lock`, and installs dependencies.

## Configuration

Copy the template and edit it (`config.yaml` is gitignored):

```bash
cp config.example.yaml config.yaml
```

Fill in your News sources, Mastodon instance + access token, and your postal code.
Set `enabled: false` on any integration you don't want.

- **News**: configure sources under `news.sources`; `default_source` picks which
  tab opens first.
  - **TTRSS** source: enable "Enable API access" in TTRSS Preferences. For
    self-signed certificates set `verify_tls: false`.
  - **Lemmy** source: set `instance` (host only) and `sort` (`TopDay`, `Hot`, …);
    anonymous by default. Optionally set `username`/`password` to log in, which
    enables `Subscribed` and your read/vote state (password can come from
    `MC_NEWS_LEMMY_PASSWORD`). A dropdown at the top of the Lemmy feed switches
    between **Subscribed / Local / All**, and each post's "N comments" count is a
    link to its comment thread on your instance. When logged in, each post shows a
    ▲/score/▼ control to up/downvote (score updates live; click your active arrow
    again to clear the vote).
- **Mastodon**: create an app in *Preferences → Development*, then copy "Your
  access token". Reading the Notifications/Home/Trending tabs needs
  `read:notifications` + `read:statuses` (or `read`); **posting from the Compose
  tab additionally needs `write:statuses`** (or `write`). Use `show_notifications`
  / `show_home` / `show_trending` / `show_compose` to choose which tabs appear.
- **Weather**: just set `location.postal_code` and `location.country` (ISO alpha-2).

### Secrets via environment variables

Any config value can be overridden by an environment variable named
`MC_<SECTION>_<KEY>` (uppercased), and the environment **always wins**. This lets
you keep structured settings in `config.yaml` while keeping secrets out of the
file — e.g. export them from your `.envrc` (also gitignored):

```bash
export MC_MASTODON_ACCESS_TOKEN=abc123
export MC_NEWS_TTRSS_PASSWORD=hunter2   # nested: news.sources.ttrss.password
```

Section names map to the config: `location` → `MC_LOCATION_*`, and each
integration by name → `MC_MASTODON_*`, `MC_WEATHER_*`. News sources nest one level
deeper as `MC_NEWS_<SOURCE>_<KEY>` (e.g. `MC_NEWS_TTRSS_PASSWORD`).

## Run

```bash
uv run morning-coffee
```

A window opens with one panel per enabled integration. Weather populates with no
credentials; TTRSS/Mastodon show a clear message in-panel if not yet configured.
Click a story/interaction to open it in your browser; "Refresh all" re-fetches.

## Adding an integration

1. Add a module under `src/morning_coffee/integrations/` with a subclass of
   `Integration` (see `base.py`); set `name` and `config_key`, implement
   `fetch() -> list[FeedItem]`.
2. Append the class to `REGISTRY` in `integrations/__init__.py`.
3. Add a config block for it under `integrations:` in `config.example.yaml`.

No UI changes are needed — the app renders one panel per registered integration.

## Credits

- Weather conditions are drawn with the [Weather Icons](https://github.com/erikflowers/weather-icons)
  font by Erik Flowers, bundled at `src/morning_coffee/assets/` and licensed under
  the SIL Open Font License 1.1 (see the accompanying `OFL.txt`).
- The title's coffee icon is the "mug-hot" glyph from
  [Font Awesome 6 Free](https://fontawesome.com) (icons under CC BY 4.0),
  subset to a single glyph and bundled at `src/morning_coffee/assets/coffee.ttf`
  (see `FONT-AWESOME-LICENSE.txt`).
