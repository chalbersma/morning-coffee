"""Normalized data model shared by every integration and the UI.

Each integration converts its source-specific payload into a list of
``FeedItem`` objects. The UI only knows how to render ``FeedItem``s, so it is
completely decoupled from where the data came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FeedItem:
    """A single row rendered in a panel.

    Attributes:
        title: Primary line (e.g. article headline, "@alice favourited", "Mon 72°/55°").
        subtitle: Secondary line (e.g. feed name + excerpt, status text, condition).
        url: Optional link the item points to.
        timestamp: Optional time associated with the item (used for ordering/display).
        source: Name of the integration that produced this item.
        meta: Free-form extra fields an integration may attach (e.g. emoji, counts).
    """

    title: str
    subtitle: str = ""
    url: str | None = None
    timestamp: datetime | None = None
    source: str = ""
    meta: dict = field(default_factory=dict)
