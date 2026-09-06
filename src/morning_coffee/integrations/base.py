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
from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import FeedItem


@dataclass
class ItemAction:
    """An action offered on each item row (e.g. "mark read").

    Attributes:
        label: Button text / accessible label (e.g. "read").
        run: Callable acting on one item; raises on error.
        icon: Optional glyph; when set the row shows a compact icon button
            instead of a text button.
        icon_font: Registered Kivy font the ``icon`` glyph belongs to.
    """

    label: str
    run: Callable[[FeedItem], None]
    icon: str | None = None
    icon_font: str | None = None


@dataclass
class BulkAction:
    """An action offered for the whole feed (e.g. "mark all read").

    Attributes:
        label: Button text (e.g. "Mark all read").
        run: Callable acting on the whole feed; raises on error.
    """

    label: str
    run: Callable[[], None]


@dataclass
class VoteAction:
    """Up/down voting on each item row (e.g. Lemmy posts).

    Attributes:
        vote: Callable ``(item, target_score) -> (new_score, new_my_vote)`` where
            target_score is 1 (up), -1 (down) or 0 (clear). Raises on error.
    """

    vote: Callable[[FeedItem, int], tuple[int, int]]


@dataclass
class FeedSelector:
    """A dropdown shown at the top of a feed to switch what it lists.

    Attributes:
        options: (label, value) choices shown in the dropdown.
        on_select: Called with the chosen value before the feed re-fetches.
        default: The value selected initially.
    """

    options: list[tuple[str, str]]
    on_select: Callable[[str], None]
    default: str


@dataclass
class FeedTab:
    """A tab that shows a scrollable list of items.

    Attributes:
        title: Short tab label (e.g. "Home").
        fetch: Callable returning items newest-first; raises on error.
        item_action: Optional per-item action rendered as a button on each row.
        bulk_action: Optional feed-wide action rendered next to the status line.
        selector: Optional dropdown that switches what the feed lists, then refetches.
        vote_action: Optional up/down vote control rendered on each row.
        default: If True, this tab is the one shown first when the panel opens.
    """

    title: str
    fetch: Callable[[], list[FeedItem]]
    item_action: ItemAction | None = None
    bulk_action: BulkAction | None = None
    selector: FeedSelector | None = None
    vote_action: VoteAction | None = None
    default: bool = False


@dataclass
class ComposeTab:
    """A tab that lets the user submit text (e.g. a new post).

    Attributes:
        title: Short tab label (e.g. "Compose").
        submit: Callable ``(text, visibility) -> None``; raises on error.
        visibilities: (label, api_value) choices for the visibility selector.
        default_visibility: api_value selected by default.
        max_characters: Soft character limit used for the counter.
        hint: Placeholder text shown in the empty input.
        default: If True, this tab is the one shown first when the panel opens.
    """

    title: str
    submit: Callable[[str, str], None]
    visibilities: list[tuple[str, str]] = field(default_factory=list)
    default_visibility: str = "public"
    max_characters: int = 500
    hint: str = "What's on your mind?"
    default: bool = False


Tab = FeedTab | ComposeTab


@dataclass
class Field:
    """A single editable setting, described for the settings screen.

    Attributes:
        key: The settings key under the integration's config block.
        label: Human-readable label shown in the form.
        kind: One of "text", "int", "bool", "secret", "choice".
        choices: Allowed values when ``kind == "choice"``.
        help: Optional hint shown near the field.
    """

    key: str
    label: str
    kind: str = "text"
    choices: list[str] | None = None
    help: str = ""


class Integration(ABC):
    """Base class for a dashboard data source.

    Class attributes:
        name: Human-readable panel title (e.g. "Top Stories").
        config_key: Key under ``integrations:`` in config.yaml (e.g. "ttrss").
    """

    name: str = "Integration"
    config_key: str = ""

    @classmethod
    def config_fields(cls) -> list[Field]:
        """Editable settings for this integration (for the settings screen).

        Default: none. Integrations override to expose their fields.
        """
        return []

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

    def tabs(self) -> list[Tab]:
        """Return this integration's tabs. Default: one feed tab over ``fetch()``.

        Integrations with a single view need not override this. Those with
        multiple views (feeds and/or a compose action) return several tabs.
        """

        def _adapter() -> list[FeedItem]:
            items = self.fetch()
            if self._error:
                raise RuntimeError(self._error)
            return items

        return [FeedTab(title=self.name, fetch=_adapter)]
