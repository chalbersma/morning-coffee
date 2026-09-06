"""Configuration loading and persistence for morning-coffee.

Settings live in ``config.yaml`` in a per-user, cross-platform data directory
(``App.user_data_dir`` / ``platformdirs.user_config_dir("morningcoffee")``), seeded
from ``config.example.yaml`` on first run. The in-app settings screen writes there.

Any value can also be overridden by an environment variable named
``MC_<SECTION>_<KEY>`` (uppercased); the environment always wins, so secrets can be
injected from the shell / ``.envrc`` instead of stored on disk.

Section mapping:
    * ``location:``            -> ``MC_LOCATION_<KEY>``     (e.g. MC_LOCATION_POSTAL_CODE)
    * ``integrations.<name>:`` -> ``MC_<NAME>_<KEY>``       (e.g. MC_MASTODON_ACCESS_TOKEN)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
import yaml

ENV_PREFIX = "MC_"
APP_NAME = "morningcoffee"

# Repo root = three levels up from this file (src/morning_coffee/config.py).
_REPO_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
# The committed template used to seed a fresh user config.
_EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.example.yaml"


def default_config_path() -> Path:
    """The writable per-user ``config.yaml`` path (cross-platform).

    Uses the running Kivy App's ``user_data_dir`` when available, else falls back
    to ``platformdirs`` (so tests/CLI need not import Kivy). Both resolve to the
    same location on desktop (e.g. ``~/Library/Application Support/morningcoffee``).
    """
    base: str | None = None
    try:  # Prefer the running App's dir; import lazily to stay Kivy-free otherwise.
        from kivy.app import App

        app = App.get_running_app()
        if app is not None:
            base = app.user_data_dir
    except Exception:  # noqa: BLE001 - fall back to platformdirs
        base = None
    if base is None:
        base = platformdirs.user_config_dir(APP_NAME)
    return Path(base) / "config.yaml"


def _resolve_path(path: str | os.PathLike | None) -> Path:
    """Resolve which config file to read, honoring explicit path and env var."""
    if path:
        return Path(path)
    if os.environ.get("MORNING_COFFEE_CONFIG"):
        return Path(os.environ["MORNING_COFFEE_CONFIG"])
    user_path = default_config_path()
    if user_path.exists():
        return user_path
    if _REPO_CONFIG_PATH.exists():  # dev convenience
        return _REPO_CONFIG_PATH
    return user_path  # non-existent user path -> triggers first-run seeding


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded."""


@dataclass
class Config:
    """Resolved configuration.

    Attributes:
        location: The ``location:`` block (postal_code, country, units, ...).
        integrations: Mapping of integration name -> its settings dict.
        path: The file the config was loaded from (for error messages).
    """

    location: dict = field(default_factory=dict)
    integrations: dict = field(default_factory=dict)
    path: Path | None = None

    def integration_settings(self, name: str) -> dict:
        """Return the settings dict for an integration, merged with location.

        Integrations frequently need location fields (weather), so we expose a
        copy of the integration's block with the ``location`` values available
        under a nested ``location`` key and also flattened in for convenience.
        """
        settings = dict(self.integrations.get(name, {}))
        settings.setdefault("location", dict(self.location))
        return settings


def _coerce_like(value: str, template):
    """Coerce a string env value to the type of an existing YAML value."""
    if isinstance(template, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(template, int):
        try:
            return int(value)
        except ValueError:
            return value
    if isinstance(template, float):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def apply_env_overrides(section_name: str, section: dict) -> None:
    """Override keys in ``section`` from ``MC_<SECTION_NAME>_<KEY>`` env vars.

    Mutates ``section`` in place. Env values are coerced to match the type of
    the existing YAML value when one is present; otherwise they stay strings.

    Public so composite integrations can apply overrides to nested settings
    (e.g. News applies ``MC_NEWS_TTRSS_*`` to its per-source dicts).
    """
    prefix = f"{ENV_PREFIX}{section_name.upper()}_"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        key = env_key[len(prefix):].lower()
        if key in section:
            section[key] = _coerce_like(env_val, section[key])
        else:
            section[key] = env_val


# Backwards-compatible private alias.
_apply_env_overrides = apply_env_overrides


def _seed_if_missing(config_path: Path) -> None:
    """On first run, create ``config_path`` from the example template."""
    if config_path.exists():
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if _EXAMPLE_CONFIG_PATH.exists():
        config_path.write_text(
            _EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:  # no template available: start from an empty scaffold
        config_path.write_text("location: {}\nintegrations: {}\n", encoding="utf-8")


def load_raw(path: str | os.PathLike | None = None) -> dict:
    """Return the plain on-disk YAML mapping (no env overrides applied).

    Seeds the file from the example template on first run. The settings screen
    edits this mapping so saving never bakes env-injected secrets into the file.
    """
    config_path = _resolve_path(path)
    _seed_if_missing(config_path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}.")
    return raw


def save_path() -> Path:
    """Where config is written: explicit env var, else the per-user location.

    Honors ``$MORNING_COFFEE_CONFIG`` so reads and writes target the same file,
    but never falls back to the committed repo template.
    """
    if os.environ.get("MORNING_COFFEE_CONFIG"):
        return Path(os.environ["MORNING_COFFEE_CONFIG"])
    return default_config_path()


def save_raw(raw: dict, path: str | os.PathLike | None = None) -> Path:
    """Write a plain config mapping to YAML at the writable path. Returns it."""
    config_path = Path(path) if path else save_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(raw, fh, sort_keys=False, allow_unicode=True)
    return config_path


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load configuration from YAML and apply environment overrides.

    Resolution order: explicit ``path`` -> ``$MORNING_COFFEE_CONFIG`` ->
    ``<user_data_dir>/config.yaml`` -> repo-root ``config.yaml`` (dev). The file is
    seeded from ``config.example.yaml`` on first run.
    """
    config_path = _resolve_path(path)
    raw = load_raw(config_path)

    location = dict(raw.get("location") or {})
    integrations = {
        name: dict(settings or {})
        for name, settings in (raw.get("integrations") or {}).items()
    }

    # Apply env overrides: location, then each integration by name.
    _apply_env_overrides("location", location)
    for name, settings in integrations.items():
        _apply_env_overrides(name, settings)

    return Config(location=location, integrations=integrations, path=config_path)


def save_config(config: Config, path: str | os.PathLike | None = None) -> Path:
    """Write a ``Config`` back to YAML (location + integrations)."""
    return save_raw(
        {"location": config.location, "integrations": config.integrations}, path
    )
