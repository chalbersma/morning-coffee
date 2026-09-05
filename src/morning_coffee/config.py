"""Configuration loading for morning-coffee.

Settings live in ``config.yaml`` at the repo root (gitignored). Any value can be
overridden by an environment variable named ``MC_<SECTION>_<KEY>`` (uppercased),
and the environment always wins. This lets you keep structured settings in YAML
while injecting secrets from your shell / ``.envrc``.

Section mapping:
    * ``location:``            -> ``MC_LOCATION_<KEY>``     (e.g. MC_LOCATION_POSTAL_CODE)
    * ``integrations.<name>:`` -> ``MC_<NAME>_<KEY>``       (e.g. MC_MASTODON_ACCESS_TOKEN)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ENV_PREFIX = "MC_"

# Repo root = three levels up from this file (src/morning_coffee/config.py).
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


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


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load configuration from YAML and apply environment overrides.

    Args:
        path: Explicit config path. Falls back to ``$MORNING_COFFEE_CONFIG`` and
            then to ``config.yaml`` at the repo root.

    Raises:
        ConfigError: If the file is missing or is not a YAML mapping.
    """
    config_path = Path(
        path
        or os.environ.get("MORNING_COFFEE_CONFIG")
        or _DEFAULT_CONFIG_PATH
    )

    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Copy config.example.yaml to config.yaml and fill it in."
        )

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}.")

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
