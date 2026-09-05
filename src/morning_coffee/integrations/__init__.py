"""Integration registry.

``REGISTRY`` is the single list the app iterates over to build panels. To add a
new data source, implement an ``Integration`` subclass in this package and append
its class here (and add a matching block to ``config.example.yaml``).
"""

from __future__ import annotations

from .base import Integration
from .lemmy import LemmyIntegration
from .mastodon import MastodonIntegration
from .news import NewsIntegration
from .ttrss import TtrssIntegration
from .weather import WeatherIntegration

# Top-level panels. TTRSS/Lemmy are not here: they are News sources (see news.py).
REGISTRY: list[type[Integration]] = [
    NewsIntegration,
    MastodonIntegration,
    WeatherIntegration,
]

__all__ = [
    "Integration",
    "REGISTRY",
    "NewsIntegration",
    "TtrssIntegration",
    "LemmyIntegration",
    "MastodonIntegration",
    "WeatherIntegration",
]
