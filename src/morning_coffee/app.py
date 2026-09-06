"""morning-coffee Kivy application entry point.

Shows one panel at a time in a swipeable carousel. A top bar navigates between
panels (‹ / › plus the panel title) and refreshes all of them; a dots row shows
the current position. Every panel also fetches once on launch.
"""

from __future__ import annotations

import sys

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.carousel import Carousel
from kivy.uix.label import Label

from .config import Config, ConfigError, load_config
from .integrations import REGISTRY
from .ui.icons import COFFEE_GLYPH, GEAR_GLYPH, ICON_FONT, register_fonts
from .ui.panel import Panel
from .ui.settings import SettingsScreen

Window.clearcolor = (0.96, 0.96, 0.97, 1)


class MorningCoffeeApp(App):
    title = "Morning Coffee"

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._panels: list[Panel] = []
        self.carousel: Carousel | None = None
        self._title_lbl: Label | None = None
        self._dot_btns: list[Button] = []
        self._body: BoxLayout | None = None  # holds carousel + dots (rebuilt on save)

    def build(self):
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))

        # Top bar: ‹  [coffee] Title  ›   [⚙] [Refresh all]
        bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6))
        prev_btn = Button(text="‹", size_hint_x=None, width=dp(40), font_size="22sp")
        prev_btn.bind(on_release=lambda _b: self._nav(-1))
        self._title_lbl = Label(
            text="",
            markup=True,
            font_size="20sp",
            halign="center",
            color=(0.1, 0.1, 0.15, 1),
        )
        next_btn = Button(text="›", size_hint_x=None, width=dp(40), font_size="22sp")
        next_btn.bind(on_release=lambda _b: self._nav(1))
        settings_btn = Button(
            text=GEAR_GLYPH, font_name=ICON_FONT,
            size_hint_x=None, width=dp(40), font_size="18sp",
        )
        settings_btn.bind(on_release=lambda _b: self._open_settings())
        refresh_btn = Button(text="Refresh all", size_hint_x=None, width=dp(110))
        refresh_btn.bind(on_release=lambda _b: self.refresh_all())
        bar.add_widget(prev_btn)
        bar.add_widget(self._title_lbl)
        bar.add_widget(next_btn)
        bar.add_widget(settings_btn)
        bar.add_widget(refresh_btn)
        root.add_widget(bar)

        # Body (carousel + dots) is built here and rebuilt after a settings save.
        self._body = BoxLayout(orientation="vertical", spacing=dp(8))
        root.add_widget(self._body)
        self._build_carousel()
        return root

    def _build_carousel(self) -> None:
        """(Re)build panels + carousel from the current config into ``self._body``."""
        self._body.clear_widgets()
        self._panels = []
        for integration_cls in REGISTRY:
            settings = self._config.integration_settings(integration_cls.config_key)
            integration = integration_cls(settings)
            if not integration.enabled:
                continue
            self._panels.append(Panel(integration))

        if not self._panels:
            self.carousel = None
            self._title_lbl.text = ""
            self._body.add_widget(
                Label(
                    text="No integrations enabled.\nOpen ⚙ to enable some.",
                    halign="center",
                    color=(0.4, 0.4, 0.45, 1),
                )
            )
            return

        self.carousel = Carousel(direction="right", loop=True)
        for panel in self._panels:
            self.carousel.add_widget(panel)
        self.carousel.bind(index=lambda _c, _i: self._on_slide())
        self._body.add_widget(self.carousel)

        # Clickable position dots: a centered row of per-panel bullet buttons.
        dots_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
        dots_row.add_widget(BoxLayout())  # left spacer (centers the dots)
        self._dot_btns = []
        for i in range(len(self._panels)):
            dot = Button(
                text="•", font_size="20sp",
                size_hint_x=None, width=dp(24),
                background_color=(0, 0, 0, 0),
            )
            dot.bind(on_release=lambda _b, idx=i: self._goto(idx))
            self._dot_btns.append(dot)
            dots_row.add_widget(dot)
        dots_row.add_widget(BoxLayout())  # right spacer
        self._body.add_widget(dots_row)
        self._on_slide()

    def _goto(self, index: int) -> None:
        if self.carousel:
            self.carousel.index = index

    def _open_settings(self) -> None:
        SettingsScreen(on_saved=self._on_settings_saved).open()

    def _on_settings_saved(self) -> None:
        try:
            self._config = load_config()
        except ConfigError:
            return
        self._build_carousel()
        self.refresh_all()

    def _nav(self, step: int) -> None:
        if not self.carousel:
            return
        if step > 0:
            self.carousel.load_next()
        else:
            self.carousel.load_previous()

    def _current_index(self) -> int:
        return self.carousel.index or 0 if self.carousel else 0

    def _on_slide(self) -> None:
        if not self.carousel or not self._panels:
            return
        idx = self._current_index()
        slide = self.carousel.current_slide
        name = slide.integration.name if slide else ""
        self._title_lbl.text = f"[b][font={ICON_FONT}]{COFFEE_GLYPH}[/font]  {name}[/b]"
        # Active dot is dark, the rest light grey. (Bullet U+2022 renders in the
        # default font; the ● / ○ circles do not.)
        for i, dot in enumerate(self._dot_btns):
            dot.color = (0.2, 0.2, 0.2, 1) if i == idx else (0.7, 0.7, 0.72, 1)

    def on_start(self):
        self.refresh_all()

    def refresh_all(self):
        for panel in self._panels:
            panel.refresh()


def main() -> int:
    """Console-script entry point."""
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    register_fonts()  # register icon fonts before any Label is built
    MorningCoffeeApp(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
