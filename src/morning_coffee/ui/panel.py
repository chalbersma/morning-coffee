"""A reusable dashboard panel that renders one integration's items.

Each panel owns one ``Integration``. Fetching happens on a background thread so
the Kivy UI thread never blocks; results are marshalled back with
``Clock.schedule_once``. The panel shows a title, a status line, and a scrollable
list of ``FeedItem`` rows.
"""

from __future__ import annotations

import threading
import webbrowser

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from ..integrations.base import Integration
from ..models import FeedItem


class ItemRow(BoxLayout):
    """A single FeedItem: clickable title over a muted subtitle."""

    def __init__(self, item: FeedItem, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            padding=(dp(6), dp(4)),
            spacing=dp(2),
            **kwargs,
        )
        self.item = item

        title = Label(
            text=self._markup_title(item),
            markup=True,
            halign="left",
            valign="top",
            size_hint_y=None,
            color=(0.15, 0.15, 0.2, 1),
        )
        title.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        title.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))

        self.add_widget(title)

        if item.subtitle:
            subtitle = Label(
                text=item.subtitle,
                halign="left",
                valign="top",
                size_hint_y=None,
                font_size="12sp",
                color=(0.4, 0.4, 0.45, 1),
            )
            subtitle.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
            subtitle.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
            self.add_widget(subtitle)

        self.bind(minimum_height=self.setter("height"))
        if item.url:
            self.bind(on_touch_down=self._maybe_open)

    @staticmethod
    def _markup_title(item: FeedItem) -> str:
        if item.url:
            return f"[b]{item.title}[/b]"
        return f"[b]{item.title}[/b]"

    def _maybe_open(self, _widget, touch):
        if self.collide_point(*touch.pos) and self.item.url:
            webbrowser.open(self.item.url)
            return True
        return False


class Panel(BoxLayout):
    """A column showing one integration's title, status, and item list."""

    def __init__(self, integration: Integration, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(4), **kwargs)
        self.integration = integration

        header = Label(
            text=f"[b]{integration.name}[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(32),
            font_size="18sp",
            color=(0.1, 0.1, 0.15, 1),
        )
        self.add_widget(header)

        self.status = Label(
            text="Loading…",
            size_hint_y=None,
            height=dp(20),
            font_size="12sp",
            color=(0.5, 0.5, 0.55, 1),
        )
        self.add_widget(self.status)

        self.scroll = ScrollView()
        self.list = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(2),
            padding=(0, dp(2)),
        )
        self.list.bind(minimum_height=self.list.setter("height"))
        self.scroll.add_widget(self.list)
        self.add_widget(self.scroll)

    def refresh(self) -> None:
        """Kick off a background fetch for this panel."""
        self.status.text = "Loading…"
        thread = threading.Thread(target=self._fetch_worker, daemon=True)
        thread.start()

    def _fetch_worker(self) -> None:
        items = self.integration.fetch()
        error = self.integration.health()
        # Marshal back to the UI thread.
        Clock.schedule_once(lambda _dt: self._render(items, error), 0)

    def _render(self, items: list[FeedItem], error: str | None) -> None:
        self.list.clear_widgets()
        if error:
            self.status.text = f"[error] {error}"
            self.status.color = (0.7, 0.2, 0.2, 1)
            return
        if not items:
            self.status.text = "No items."
            self.status.color = (0.5, 0.5, 0.55, 1)
            return
        self.status.text = f"{len(items)} item(s)"
        self.status.color = (0.5, 0.5, 0.55, 1)
        for item in items:
            self.list.add_widget(ItemRow(item))
