"""Settings overlay: edit config in-app and write it to disk.

Renders a scrollable form built from each integration's ``config_fields()`` plus a
Location section. Values are read from and written back to the raw on-disk YAML
mapping (``config.load_raw`` / ``config.save_raw``), so env-injected secrets are
never baked into the file. Secrets are masked; a blank secret field leaves the
stored value untouched.
"""

from __future__ import annotations

from kivy.metrics import dp
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput

from ..config import load_raw, save_raw
from ..integrations import REGISTRY
from ..integrations.base import Field

# Location fields aren't owned by an integration; describe them here.
LOCATION_FIELDS = [
    Field("postal_code", "Postal code"),
    Field("country", "Country", help="ISO alpha-2, e.g. us"),
    Field("units", "Units", kind="choice", choices=["fahrenheit", "celsius"]),
]

_LABEL_COLOR = (0.15, 0.15, 0.2, 1)
_MUTED = (0.45, 0.45, 0.5, 1)


class _FieldRow(BoxLayout):
    """One label + input widget; exposes get_value()/is_blank for saving."""

    def __init__(self, field: Field, value, **kwargs):
        super().__init__(
            orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(8), **kwargs
        )
        self.field = field
        self.add_widget(
            Label(
                text=field.label,
                size_hint_x=0.4,
                halign="left",
                valign="middle",
                color=_LABEL_COLOR,
            )
        )
        self._kind = field.kind
        if field.kind == "bool":
            self._widget = Switch(active=bool(value), size_hint_x=0.6)
        elif field.kind == "choice":
            choices = field.choices or []
            self._widget = Spinner(
                text=str(value) if value not in (None, "") else (choices[0] if choices else ""),
                values=choices,
                size_hint_x=0.6,
            )
        else:  # text | int | secret
            self._widget = TextInput(
                text="" if (value is None or field.kind == "secret") else str(value),
                multiline=False,
                password=(field.kind == "secret"),
                input_filter=("int" if field.kind == "int" else None),
                hint_text="leave blank to keep current" if field.kind == "secret" else "",
                size_hint_x=0.6,
            )
        self.add_widget(self._widget)

    def is_blank(self) -> bool:
        return self._kind == "secret" and not self._widget.text.strip()

    def get_value(self):
        if self._kind == "bool":
            return bool(self._widget.active)
        if self._kind == "choice":
            return self._widget.text
        text = self._widget.text.strip()
        if self._kind == "int":
            try:
                return int(text)
            except ValueError:
                return text
        return text


class SettingsScreen(ModalView):
    """Full-window settings overlay. Calls ``on_saved`` after a successful save."""

    def __init__(self, on_saved=None, **kwargs):
        # ModalView's default background is a dark overlay; use a plain light one
        # so the dark form text is readable.
        super().__init__(
            size_hint=(0.95, 0.95),
            auto_dismiss=False,
            background="",
            background_color=(0, 0, 0, 0),
            **kwargs,
        )
        self._on_saved = on_saved
        self._raw = load_raw()
        self._rows: list[tuple[str | None, str, _FieldRow]] = []  # (section, key, row)

        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        # Solid light panel behind the content.
        with root.canvas.before:
            Color(0.97, 0.97, 0.98, 1)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(
            pos=lambda w, _v: setattr(self._bg, "pos", w.pos),
            size=lambda w, _v: setattr(self._bg, "size", w.size),
        )
        root.add_widget(
            Label(
                text="[b]Settings[/b]", markup=True, size_hint_y=None, height=dp(30),
                font_size="20sp", color=_LABEL_COLOR,
            )
        )

        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4), padding=(0, dp(4)))
        form.bind(minimum_height=form.setter("height"))

        location = self._raw.setdefault("location", {})
        self._add_section(form, "Location", None, LOCATION_FIELDS, location)

        integrations = self._raw.setdefault("integrations", {})
        for cls in REGISTRY:
            block = integrations.setdefault(cls.config_key, {})
            self._add_section(
                form, cls.name, cls.config_key, cls.config_fields(), block,
                enabled=bool(block.get("enabled", True)),
            )

        scroll.add_widget(form)
        root.add_widget(scroll)

        note = Label(
            text="Secrets are stored as plain text in this config file.",
            size_hint_y=None, height=dp(20), font_size="11sp", color=_MUTED,
        )
        root.add_widget(note)

        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        cancel = Button(text="Cancel")
        cancel.bind(on_release=lambda _b: self.dismiss())
        save = Button(text="Save")
        save.bind(on_release=lambda _b: self._save())
        buttons.add_widget(cancel)
        buttons.add_widget(save)
        root.add_widget(buttons)

        self.add_widget(root)

    def _add_section(self, form, title, section_key, fields, block, enabled=None):
        form.add_widget(
            Label(
                text=f"[b]{title}[/b]", markup=True, size_hint_y=None, height=dp(28),
                halign="left", valign="middle", color=_LABEL_COLOR,
            )
        )
        # Per-integration enabled toggle.
        if section_key is not None:
            row = _FieldRow(Field("enabled", "Enabled", kind="bool"), enabled)
            self._rows.append((section_key, "enabled", row))
            form.add_widget(row)
        for f in fields:
            row = _FieldRow(f, block.get(f.key))
            self._rows.append((section_key, f.key, row))
            form.add_widget(row)

    def _save(self):
        location = self._raw.setdefault("location", {})
        integrations = self._raw.setdefault("integrations", {})
        for section_key, key, row in self._rows:
            if row.is_blank():  # blank secret: keep existing value
                continue
            target = location if section_key is None else integrations.setdefault(section_key, {})
            target[key] = row.get_value()
        save_raw(self._raw)
        self.dismiss()
        if self._on_saved:
            self._on_saved()
