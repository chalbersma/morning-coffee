"""The extension point for morning-coffee data sources.

Every data source is an ``Integration`` subclass. To add a new source:

    1. Subclass ``Integration``, set ``name`` and ``config_key``.
    2. Implement ``fetch()`` to return a list of ``FeedItem``.
    3. Append the class to ``REGISTRY`` in ``integrations/__init__.py`` and add a
       block for it to ``config.example.yaml``.

The UI renders one panel per registered+enabled integration and never needs to
change when a new one is added.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import FeedItem


class Integration(ABC):
    """Base class for a dashboard data source.

    Class attributes:
        name: Human-readable panel title (e.g. "Top Stories").
        config_key: Key under ``integrations:`` in config.yaml (e.g. "ttrss").
    """

    name: str = "Integration"
    config_key: str = ""

    def __init__(self, settings: dict) -> None:
        """Store this integration's slice of config.

        Args:
            settings: The integration's block from config, with a nested
                ``location`` dict merged in (see ``Config.integration_settings``).
        """
        self.settings = settings or {}
        self._error: str | None = None

    @property
    def enabled(self) -> bool:
        """Whether this integration should be shown/fetched."""
        return bool(self.settings.get("enabled", True))

    @abstractmethod
    def fetch(self) -> list[FeedItem]:
        """Fetch and normalize items, newest first.

        Implementations should raise on failure; the caller records the error
        and surfaces it via ``health()``.
        """
        raise NotImplementedError

    def health(self) -> str | None:
        """Return the last error string, if any, for display in the panel."""
        return self._error
