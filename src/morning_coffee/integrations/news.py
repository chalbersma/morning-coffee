"""News aggregator: one panel that switches between news sources.

Each configured source (TTRSS, Lemmy, ...) is itself an ``Integration`` that
returns a single ``FeedTab``. ``NewsIntegration`` instantiates each enabled source
and collects those tabs, so the panel renders one tab per source (using the same
button-row toggle as any multi-tab panel). Sources keep their own behavior — e.g.
TTRSS keeps its mark-as-read item/bulk actions.

Add a new source type by writing an ``Integration`` and registering it in
``SOURCE_TYPES`` (and adding a block under ``news.sources`` in config).
"""

from __future__ import annotations

from ..config import apply_env_overrides
from ..models import FeedItem
from .base import FeedTab, Integration, Tab
from .lemmy import LemmyIntegration
from .ttrss import TtrssIntegration

# Source type name (from ``sources.<name>.type``) -> Integration subclass.
SOURCE_TYPES: dict[str, type[Integration]] = {
    "ttrss": TtrssIntegration,
    "lemmy": LemmyIntegration,
}


class NewsIntegration(Integration):
    name = "News"
    config_key = "news"

    def fetch(self) -> list[FeedItem]:
        """Not used directly: News is a multi-tab panel (see ``tabs()``)."""
        return []

    def tabs(self) -> list[Tab]:
        sources = self.settings.get("sources") or {}
        default_source = self.settings.get("default_source")

        tabs: list[Tab] = []
        for src_name, raw in sources.items():
            cfg = dict(raw or {})
            if not cfg.get("enabled", True):
                continue
            src_type = cfg.get("type", src_name)
            cls = SOURCE_TYPES.get(src_type)
            if cls is None:
                continue  # unknown source type: skip rather than crash

            # Inject nested per-source secrets: MC_NEWS_<SOURCE>_<KEY>.
            apply_env_overrides(f"news_{src_name}", cfg)

            source = cls(cfg)
            source_tabs = source.tabs()
            if not source_tabs:
                continue
            tab = source_tabs[0]
            tab.title = cfg.get("title", source.name)
            tab.default = src_name == default_source
            tabs.append(tab)

        return tabs
