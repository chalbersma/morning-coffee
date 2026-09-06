# morning-coffee
A Test of AI capabilities, want to make a "morning coffee" app that gives me the info I want to start the day.

A small [Kivy](https://kivy.org) desktop dashboard, managed with [uv](https://docs.astral.sh/uv/).
It shows **one panel at a time**; navigate between them with the ‹ / › arrows in the
top bar or by swiping (the dots show your position). The panels:

- **Top Stories** — headlines from your [Tiny Tiny RSS](https://tt-rss.org) instance;
  mark a story read with its checkmark button or clear the feed with "Mark all read"
  (both write back to the server).
- **Lemmy** — top posts from a [Lemmy](https://join-lemmy.org) instance (anonymous, or
  logged in). Switch between Subscribed / Local / All, follow the comments link, and —
  when logged in — up/downvote with the ▲/▼ control.
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

Edit settings **in the app** via the **⚙ button** in the top bar: it shows a form for
Location and every integration (URLs, instances, limits, toggles, credentials), and
Save writes the config to disk and reloads the panels.

Config is stored per-user in a cross-platform location, seeded from
`config.example.yaml` on first run:

- macOS: `~/Library/Application Support/morningcoffee/config.yaml`
- Linux: `~/.config/morningcoffee/config.yaml`
- Windows: `%APPDATA%\morningcoffee\config.yaml`

You can still edit that YAML by hand, keep a `config.yaml` beside the example for local
dev, or point `$MORNING_COFFEE_CONFIG` at an explicit path. Set `enabled: false` (or the
Enabled toggle) on any integration you don't want.

Notes per integration:

- **TTRSS**: enable "Enable API access" in TTRSS Preferences. For self-signed
  certificates set `verify_tls: false`.
- **Lemmy**: set `instance` (host only) and `sort` (`TopDay`, `Hot`, …); anonymous by
  default. Optionally set `username`/`password` to log in, which enables `Subscribed`
  and your read/vote state (password can come from `MC_LEMMY_PASSWORD`). A dropdown at
  the top of the feed switches between **Subscribed / Local / All**, each post's
  "N comments" count links to its comment thread, and when logged in each post shows a
  ▲/score/▼ control to up/downvote (score updates live; click your active arrow again
  to clear the vote).
- **Mastodon**: create an app in *Preferences → Development*, then copy "Your
  access token". Reading the Notifications/Home/Trending tabs needs
  `read:notifications` + `read:statuses` (or `read`); **posting from the Compose
  tab additionally needs `write:statuses`** (or `write`). Use `show_notifications`
  / `show_home` / `show_trending` / `show_compose` to choose which tabs appear.
- **Weather**: just set `location.postal_code` and `location.country` (ISO alpha-2).

### Secrets

Secrets (passwords, tokens) are saved in the config file as **plain text** — the file
lives in your per-user directory above. The settings screen masks them and only writes
a secret when you type a new value (blank leaves the stored one untouched).

Alternatively, any config value can be overridden by an environment variable named
`MC_<SECTION>_<KEY>` (uppercased), and the environment **always wins** — so you can keep
secrets out of the file entirely by exporting them from your `.envrc`:

```bash
export MC_MASTODON_ACCESS_TOKEN=abc123
export MC_TTRSS_PASSWORD=hunter2
export MC_LEMMY_PASSWORD=hunter2
```

Section names map to the config: `location` → `MC_LOCATION_*`, and each integration
by name → `MC_TTRSS_*`, `MC_LEMMY_*`, `MC_MASTODON_*`, `MC_WEATHER_*`.

## Run

```bash
uv run morning-coffee
```

A window opens showing one panel at a time; use the ‹ / › arrows or swipe to move
between them (the dots show your position, and it wraps around). Weather populates
with no credentials; TTRSS/Mastodon show a clear message in-panel if not yet
configured. Click a story/interaction to open it in your browser; "Refresh all"
re-fetches every panel; ⚙ opens the settings screen.

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
