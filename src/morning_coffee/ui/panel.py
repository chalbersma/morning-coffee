"""Dashboard panels and their tab views.

An integration declares one or more tabs (see ``integrations/base.py``). Each
``FeedTab`` renders as a ``FeedView`` (a scrollable list) and each ``ComposeTab``
as a ``ComposeView`` (a text form). A ``Panel`` shows one integration: if it has a
single tab the view fills the column; with several tabs a button row toggles
between them.

All network work happens on background threads; results are marshalled back to
the Kivy UI thread with ``Clock.schedule_once``. Widgets are never touched off
the UI thread.
"""

from __future__ import annotations

import threading
import webbrowser

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import escape_markup

from ..integrations.base import ComposeTab, FeedTab, Integration
from ..models import FeedItem
from .icons import CARET_DOWN_GLYPH, CARET_UP_GLYPH, ICON_FONT


class ItemRow(BoxLayout):
    """A single FeedItem: clickable text with an optional action button.

    ``on_action`` is called with this row when its action button is pressed.
    """

    def __init__(self, item: FeedItem, action=None, on_action=None,
                 vote_action=None, on_vote_error=None, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            padding=(dp(6), dp(4)),
            spacing=dp(6),
            **kwargs,
        )
        self.item = item
        self._on_action = on_action
        self.action_btn: Button | None = None
        self._subtitle: Label | None = None
        self._sub_links: dict[str, str] = {}
        self._vote_action = vote_action
        self._on_vote_error = on_vote_error
        self._vote_control = None

        # Optional leading icon (e.g. a weather glyph from a registered icon font).
        if item.icon:
            icon = Label(
                text=item.icon,
                font_name=item.icon_font,
                font_size="26sp",
                size_hint_x=None,
                width=dp(34),
                halign="center",
                valign="middle",
                color=(0.15, 0.15, 0.2, 1),
            )
            icon.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
            self.add_widget(icon)

        # Text column (title over optional subtitle).
        text_col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))

        title = Label(
            text=f"[b]{item.title}[/b]",
            markup=True,
            halign="left",
            valign="top",
            size_hint_y=None,
            color=(0.15, 0.15, 0.2, 1),
        )
        title.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        title.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
        text_col.add_widget(title)

        if item.subtitle_segments:
            # Render segments; those with a url become clickable [ref] links.
            parts = []
            for i, (text, url) in enumerate(item.subtitle_segments):
                safe = escape_markup(text)
                if url:
                    ref = str(i)
                    self._sub_links[ref] = url
                    parts.append(f"[ref={ref}][color=3b6ea5]{safe}[/color][/ref]")
                else:
                    parts.append(safe)
            self._subtitle = Label(
                text="".join(parts),
                markup=True,
                halign="left",
                valign="top",
                size_hint_y=None,
                font_size="12sp",
                color=(0.4, 0.4, 0.45, 1),
            )
            self._subtitle.bind(on_ref_press=self._on_ref_press)
            self._subtitle.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
            self._subtitle.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))
        elif item.subtitle:
            self._subtitle = Label(
                text=item.subtitle,
                halign="left",
                valign="top",
                size_hint_y=None,
                font_size="12sp",
                color=(0.4, 0.4, 0.45, 1),
            )
            self._subtitle.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
            self._subtitle.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1]))

        # Second line: subtitle on the left, optional vote control inline on the
        # right. Keeping the control here (rather than a full-height right column)
        # lets the title use the full row width instead of wrapping.
        control = self._build_vote_control() if vote_action else None
        if self._subtitle and control:
            line2 = BoxLayout(orientation="horizontal", size_hint_y=None, spacing=dp(6))
            line2.add_widget(self._subtitle)
            line2.add_widget(control)
            line2.bind(minimum_height=line2.setter("height"))
            text_col.add_widget(line2)
        elif self._subtitle:
            text_col.add_widget(self._subtitle)
        elif control:
            text_col.add_widget(control)

        text_col.bind(minimum_height=text_col.setter("height"))
        self._text_col = text_col
        self.add_widget(text_col)

        if action and on_action:
            if action.icon:
                # Compact square icon button (e.g. a checkmark to mark read).
                self.action_btn = Button(
                    text=action.icon,
                    font_name=action.icon_font,
                    size_hint=(None, None),
                    width=dp(30),
                    height=dp(30),
                    font_size="15sp",
                )
                btn_w = dp(30)
            else:
                # Text button (backward-compatible fallback).
                self.action_btn = Button(
                    text=action.label,
                    size_hint=(None, None),
                    width=dp(80),
                    height=dp(30),
                    font_size="12sp",
                )
                btn_w = dp(80)
            self.action_btn.bind(on_release=lambda _b: self._on_action(self))
            # Anchor the button to the top-right of the row.
            holder = BoxLayout(orientation="vertical", size_hint_x=None, width=btn_w)
            holder.add_widget(self.action_btn)
            holder.add_widget(BoxLayout())  # spacer pushes the button up
            self.add_widget(holder)

        # Row height follows the text column (its natural, wrapped height).
        text_col.bind(height=self._sync_height)
        self._sync_height()
        if item.url:
            self.bind(on_touch_down=self._maybe_open)

    # --- vote control --------------------------------------------------------

    _NEUTRAL = (0.5, 0.5, 0.55, 1)
    _UP = (0.85, 0.45, 0.1, 1)     # orange when upvoted
    _DOWN = (0.3, 0.45, 0.8, 1)    # blue when downvoted

    def _build_vote_control(self) -> BoxLayout:
        """Build the inline ( ▲ score ▼ ) control and return it."""
        self._score = int(self.item.meta.get("score") or 0)
        self._my_vote = int(self.item.meta.get("my_vote") or 0)

        control = BoxLayout(
            orientation="horizontal", size_hint=(None, None), width=dp(92), height=dp(20)
        )
        self._up_btn = Button(
            text=CARET_UP_GLYPH, font_name=ICON_FONT, font_size="15sp",
            size_hint_x=None, width=dp(24), background_color=(0, 0, 0, 0),
        )
        self._up_btn.bind(on_release=lambda _b: self._do_vote(1))
        self._score_lbl = Label(
            text=str(self._score), font_size="12sp", size_hint_x=None, width=dp(44),
            halign="center", valign="middle", color=self._NEUTRAL,
        )
        self._score_lbl.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        self._down_btn = Button(
            text=CARET_DOWN_GLYPH, font_name=ICON_FONT, font_size="15sp",
            size_hint_x=None, width=dp(24), background_color=(0, 0, 0, 0),
        )
        self._down_btn.bind(on_release=lambda _b: self._do_vote(-1))
        control.add_widget(self._up_btn)
        control.add_widget(self._score_lbl)
        control.add_widget(self._down_btn)
        self._vote_control = control
        self._render_vote()
        return control

    def _render_vote(self) -> None:
        self._score_lbl.text = str(self._score)
        self._up_btn.color = self._UP if self._my_vote == 1 else self._NEUTRAL
        self._down_btn.color = self._DOWN if self._my_vote == -1 else self._NEUTRAL

    def _do_vote(self, direction: int) -> None:
        if not self._vote_action:
            return
        # Clicking the active arrow again clears the vote (target 0).
        target = 0 if self._my_vote == direction else direction
        self._up_btn.disabled = True
        self._down_btn.disabled = True
        threading.Thread(target=self._vote_worker, args=(target,), daemon=True).start()

    def _vote_worker(self, target: int) -> None:
        try:
            new_score, new_my_vote = self._vote_action.vote(self.item, target)
            error = None
        except Exception as exc:  # noqa: BLE001 - report failure in the view
            new_score, new_my_vote, error = None, None, str(exc)
        Clock.schedule_once(
            lambda _dt: self._vote_done(new_score, new_my_vote, error), 0
        )

    def _vote_done(self, new_score, new_my_vote, error) -> None:
        self._up_btn.disabled = False
        self._down_btn.disabled = False
        if error:
            if self._on_vote_error:
                self._on_vote_error(error)
            return
        self._score = int(new_score)
        self._my_vote = int(new_my_vote)
        self.item.meta["score"] = self._score
        self.item.meta["my_vote"] = self._my_vote
        self._render_vote()

    def _sync_height(self, *_args) -> None:
        self.height = max(self._text_col.height, dp(34))

    def _on_ref_press(self, _label, ref):
        url = self._sub_links.get(ref)
        if url:
            webbrowser.open(url)

    def _maybe_open(self, _widget, touch):
        # Don't open the article when the tap lands on the action button.
        if self.action_btn and self.action_btn.collide_point(*touch.pos):
            return False
        # Or on the subtitle when it carries its own links (Label handles those).
        if self._sub_links and self._subtitle and self._subtitle.collide_point(*touch.pos):
            return False
        # Or on the vote control (its buttons handle their own presses).
        if self._vote_control and self._vote_control.collide_point(*touch.pos):
            return False
        if self.collide_point(*touch.pos) and self.item.url:
            webbrowser.open(self.item.url)
            return True
        return False


class FeedView(BoxLayout):
    """A scrollable list backed by a ``FeedTab``, fetched off-thread.

    Renders an optional per-item action button and an optional feed-wide
    "bulk" action button next to the status line.
    """

    def __init__(self, tab: FeedTab, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(4), **kwargs)
        self._fetch = tab.fetch
        self._item_action = tab.item_action
        self._bulk_action = tab.bulk_action
        self._selector = tab.selector
        self._vote_action = tab.vote_action
        self._count = 0

        self.status = Label(
            text="Loading…",
            size_hint_y=None,
            height=dp(20),
            font_size="12sp",
            halign="left",
            color=(0.5, 0.5, 0.55, 1),
        )
        self.status.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        self.bulk_btn = None

        if self._selector or self._bulk_action:
            # A control row: [selector] status [bulk button].
            top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(6))
            if self._selector:
                self._label_by_value = {v: lbl for lbl, v in self._selector.options}
                self._value_by_label = {lbl: v for lbl, v in self._selector.options}
                default_label = self._label_by_value.get(
                    self._selector.default,
                    self._selector.options[0][0] if self._selector.options else "",
                )
                spinner = Spinner(
                    text=default_label,
                    values=[lbl for lbl, _v in self._selector.options],
                    size_hint_x=None,
                    width=dp(130),
                    font_size="12sp",
                )
                spinner.bind(text=self._on_select)
                top.add_widget(spinner)
            top.add_widget(self.status)
            if self._bulk_action:
                self.bulk_btn = Button(
                    text=self._bulk_action.label,
                    size_hint_x=None,
                    width=dp(120),
                    font_size="12sp",
                )
                self.bulk_btn.bind(on_release=lambda _b: self._on_bulk())
                top.add_widget(self.bulk_btn)
            self.add_widget(top)
        else:
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

    def _on_select(self, _spinner, label: str) -> None:
        """Selector changed: tell the source, then re-fetch."""
        if not self._selector:
            return
        value = self._value_by_label.get(label, label)
        self._selector.on_select(value)
        self.refresh()

    def refresh(self) -> None:
        """Kick off a background fetch."""
        self.status.text = "Loading…"
        self.status.color = (0.5, 0.5, 0.55, 1)
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self) -> None:
        try:
            items = self._fetch()
            error = None
        except Exception as exc:  # noqa: BLE001 - report failure in the view
            items, error = [], str(exc)
        Clock.schedule_once(lambda _dt: self._render(items, error), 0)

    def _render(self, items: list[FeedItem], error: str | None) -> None:
        self.list.clear_widgets()
        if error:
            self.status.text = f"[error] {error}"
            self.status.color = (0.7, 0.2, 0.2, 1)
            return
        if not items:
            self._count = 0
            self.status.text = "No items."
            self.status.color = (0.5, 0.5, 0.55, 1)
            return
        self._count = len(items)
        self._update_count()
        for item in items:
            self.list.add_widget(
                ItemRow(
                    item,
                    action=self._item_action,
                    on_action=self._do_item_action,
                    vote_action=self._vote_action,
                    on_vote_error=self._vote_error,
                )
            )

    def _vote_error(self, msg: str) -> None:
        self.status.text = f"[error] {msg}"
        self.status.color = (0.7, 0.2, 0.2, 1)

    def _update_count(self) -> None:
        self.status.text = f"{self._count} item(s)"
        self.status.color = (0.5, 0.5, 0.55, 1)

    # --- per-item action (optimistic remove) ---------------------------------

    def _do_item_action(self, row: "ItemRow") -> None:
        if not self._item_action:
            return
        if row.action_btn:
            row.action_btn.disabled = True
        threading.Thread(
            target=self._item_action_worker, args=(row,), daemon=True
        ).start()

    def _item_action_worker(self, row: "ItemRow") -> None:
        try:
            self._item_action.run(row.item)
            error = None
        except Exception as exc:  # noqa: BLE001 - report failure in the view
            error = str(exc)
        Clock.schedule_once(lambda _dt: self._item_action_done(row, error), 0)

    def _item_action_done(self, row: "ItemRow", error: str | None) -> None:
        if error:
            if row.action_btn:
                row.action_btn.disabled = False
            self.status.text = f"[error] {error}"
            self.status.color = (0.7, 0.2, 0.2, 1)
            return
        self.list.remove_widget(row)
        self._count = max(0, self._count - 1)
        self._update_count()

    # --- bulk action ---------------------------------------------------------

    def _on_bulk(self) -> None:
        if not self._bulk_action:
            return
        self.bulk_btn.disabled = True
        threading.Thread(target=self._bulk_worker, daemon=True).start()

    def _bulk_worker(self) -> None:
        try:
            self._bulk_action.run()
            error = None
        except Exception as exc:  # noqa: BLE001 - report failure in the view
            error = str(exc)
        Clock.schedule_once(lambda _dt: self._bulk_done(error), 0)

    def _bulk_done(self, error: str | None) -> None:
        self.bulk_btn.disabled = False
        if error:
            self.status.text = f"[error] {error}"
            self.status.color = (0.7, 0.2, 0.2, 1)
            return
        self.list.clear_widgets()
        self._count = 0
        self.status.text = "All read."
        self.status.color = (0.5, 0.5, 0.55, 1)


class ComposeView(BoxLayout):
    """A text form that submits via a ``ComposeTab`` off-thread."""

    def __init__(self, tab: ComposeTab, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(4), padding=(0, dp(2)), **kwargs)
        self.tab = tab
        self._max = tab.max_characters

        self.input = TextInput(
            hint_text=tab.hint,
            multiline=True,
            font_size="14sp",
        )
        self.input.bind(text=self._update_count)
        self.add_widget(self.input)

        self.count = Label(
            text=f"0 / {self._max}",
            size_hint_y=None,
            height=dp(20),
            font_size="12sp",
            halign="left",
            color=(0.5, 0.5, 0.55, 1),
        )
        self.count.bind(size=lambda w, *_: setattr(w, "text_size", (w.width, None)))
        self.add_widget(self.count)

        # Visibility selector + Post button on one row.
        controls = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6))
        self._vis_labels = [label for label, _value in tab.visibilities]
        self._vis_by_label = {label: value for label, value in tab.visibilities}
        default_label = next(
            (label for label, value in tab.visibilities if value == tab.default_visibility),
            self._vis_labels[0] if self._vis_labels else "Public",
        )
        self.visibility = Spinner(
            text=default_label,
            values=self._vis_labels,
        )
        controls.add_widget(self.visibility)

        self.post_btn = Button(text="Post", size_hint_x=None, width=dp(90), disabled=True)
        self.post_btn.bind(on_release=lambda _b: self._on_post())
        controls.add_widget(self.post_btn)
        self.add_widget(controls)

    def _update_count(self, _widget, value: str) -> None:
        length = len(value)
        self.count.text = f"{length} / {self._max}"
        over = length > self._max
        self.count.color = (0.7, 0.2, 0.2, 1) if over else (0.5, 0.5, 0.55, 1)
        self.post_btn.disabled = not value.strip() or over

    def _on_post(self) -> None:
        text = self.input.text.strip()
        if not text:
            return
        visibility = self._vis_by_label.get(self.visibility.text, "public")
        self.post_btn.disabled = True
        self.post_btn.text = "Posting…"
        threading.Thread(
            target=self._post_worker, args=(text, visibility), daemon=True
        ).start()

    def _post_worker(self, text: str, visibility: str) -> None:
        try:
            self.tab.submit(text, visibility)
            error = None
        except Exception as exc:  # noqa: BLE001 - report failure in the view
            error = str(exc)
        Clock.schedule_once(lambda _dt: self._post_done(error), 0)

    def _post_done(self, error: str | None) -> None:
        self.post_btn.text = "Post"
        if error:
            self.count.text = f"[error] {error}"
            self.count.color = (0.7, 0.2, 0.2, 1)
            self.post_btn.disabled = False
        else:
            self.input.text = ""  # also resets the counter via its bind
            self.count.text = "Posted!"
            self.count.color = (0.2, 0.5, 0.2, 1)
            self.post_btn.disabled = True


class Panel(BoxLayout):
    """A column showing one integration, with a tab row when it has >1 tab."""

    def __init__(self, integration: Integration, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(4), **kwargs)
        self.integration = integration
        self._feed_views: list[FeedView] = []

        header = Label(
            text=f"[b]{integration.name}[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(32),
            font_size="18sp",
            color=(0.1, 0.1, 0.15, 1),
        )
        self.add_widget(header)

        tabs = integration.tabs()
        self._views = [self._make_view(tab) for tab in tabs]

        if len(self._views) <= 1:
            # Single view fills the column, exactly like before.
            if self._views:
                self.add_widget(self._views[0])
            return

        # Pick the tab flagged default (first one wins); fall back to index 0.
        default_index = next(
            (i for i, tab in enumerate(tabs) if getattr(tab, "default", False)), 0
        )

        # Multiple views: a button row toggles which is shown.
        group = f"tabs_{id(self)}"
        tabbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(2))
        for i, tab in enumerate(tabs):
            btn = ToggleButton(text=tab.title, group=group, font_size="12sp")
            btn.bind(on_release=lambda _b, idx=i: self._show(idx))
            if i == default_index:
                btn.state = "down"
            tabbar.add_widget(btn)
        self.add_widget(tabbar)

        self._content = BoxLayout()
        self.add_widget(self._content)
        self._show(default_index)

    def _make_view(self, tab):
        if isinstance(tab, FeedTab):
            view = FeedView(tab)
            self._feed_views.append(view)
            return view
        if isinstance(tab, ComposeTab):
            return ComposeView(tab)
        raise TypeError(f"Unknown tab type: {type(tab).__name__}")

    def _show(self, index: int) -> None:
        self._content.clear_widgets()
        self._content.add_widget(self._views[index])

    def refresh(self) -> None:
        """Refresh every feed view (compose views have nothing to fetch)."""
        for view in self._feed_views:
            view.refresh()
