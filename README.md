# morning-coffee
A Test of AI capabilities, want to make a "morning coffee" app that gives me the info I want to start the day.

A small [Kivy](https://kivy.org) desktop dashboard, managed with [uv](https://docs.astral.sh/uv/),
that on launch shows three panels:

- **Top Stories** — recent headlines from your [Tiny Tiny RSS](https://tt-rss.org) instance.
- **Interactions** — recent Mastodon notifications (mentions, favourites, boosts, follows).
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

Fill in your TTRSS URL/credentials, Mastodon instance + access token, and your
postal code. Set `enabled: false` on any integration you don't want.

- **TTRSS**: enable "Enable API access" in TTRSS Preferences. For self-signed
  certificates set `verify_tls: false`.
- **Mastodon**: create an app in *Preferences → Development*, then copy "Your
  access token" (scope `read` or `read:notifications`).
- **Weather**: just set `location.postal_code` and `location.country` (ISO alpha-2).

### Secrets via environment variables

Any config value can be overridden by an environment variable named
`MC_<SECTION>_<KEY>` (uppercased), and the environment **always wins**. This lets
you keep structured settings in `config.yaml` while keeping secrets out of the
file — e.g. export them from your `.envrc` (also gitignored):

```bash
export MC_TTRSS_PASSWORD=hunter2
export MC_MASTODON_ACCESS_TOKEN=abc123
```

Section names map to the config: `location` → `MC_LOCATION_*`, and each
integration by name → `MC_TTRSS_*`, `MC_MASTODON_*`, `MC_WEATHER_*`.

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
