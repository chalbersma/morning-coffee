"""morning-coffee Kivy application entry point.

Builds one ``Panel`` per registered+enabled integration and lays them out side by
side. A "Refresh all" button re-fetches every panel; all panels also fetch once
on launch.
"""

from __future__ import annotations

import sys

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from .config import Config, ConfigError, load_config
from .integrations import REGISTRY
from .ui.panel import Panel

Window.clearcolor = (0.96, 0.96, 0.97, 1)


class MorningCoffeeApp(App):
    title = "Morning Coffee"

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._panels: list[Panel] = []

    def build(self):
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))

        # Top bar: title + refresh button.
        bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        bar.add_widget(
            Label(
                text="[b]☕ Morning Coffee[/b]",
                markup=True,
                font_size="20sp",
                halign="left",
                color=(0.1, 0.1, 0.15, 1),
            )
        )
        refresh_btn = Button(text="Refresh all", size_hint_x=None, width=dp(120))
        refresh_btn.bind(on_release=lambda _btn: self.refresh_all())
        bar.add_widget(refresh_btn)
        root.add_widget(bar)

        # One panel per enabled integration.
        panels_row = BoxLayout(orientation="horizontal", spacing=dp(12))
        for integration_cls in REGISTRY:
            settings = self._config.integration_settings(integration_cls.config_key)
            integration = integration_cls(settings)
            if not integration.enabled:
                continue
            panel = Panel(integration)
            self._panels.append(panel)
            panels_row.add_widget(panel)

        if not self._panels:
            panels_row.add_widget(
                Label(
                    text="No integrations enabled.\nEdit config.yaml to enable some.",
                    halign="center",
                    color=(0.4, 0.4, 0.45, 1),
                )
            )
        root.add_widget(panels_row)
        return root

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
    MorningCoffeeApp(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
