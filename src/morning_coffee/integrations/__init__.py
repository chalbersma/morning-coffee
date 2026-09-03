"""Integration registry.

``REGISTRY`` is the single list the app iterates over to build panels. To add a
new data source, implement an ``Integration`` subclass in this package and append
its class here (and add a matching block to ``config.example.yaml``).
"""

from __future__ import annotations

from .base import Integration
from .mastodon import MastodonIntegration
from .ttrss import TtrssIntegration
from .weather import WeatherIntegration

REGISTRY: list[type[Integration]] = [
    TtrssIntegration,
    MastodonIntegration,
    WeatherIntegration,
]

__all__ = [
    "Integration",
    "REGISTRY",
    "TtrssIntegration",
    "MastodonIntegration",
    "WeatherIntegration",
]
