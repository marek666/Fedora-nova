from __future__ import annotations

from gi.repository import Gio, GLib

from .constants import APP_ID


class WindowState:
    def __init__(self) -> None:
        self.settings: Gio.Settings | None
        try:
            self.settings = Gio.Settings.new(APP_ID)
        except GLib.Error:
            self.settings = None

    def get_int(self, key: str, default: int) -> int:
        return self.settings.get_int(key) if self.settings else default

    def get_bool(self, key: str, default: bool) -> bool:
        return self.settings.get_boolean(key) if self.settings else default

    def get_string(self, key: str, default: str) -> str:
        return self.settings.get_string(key) if self.settings else default

    def set_int(self, key: str, value: int) -> None:
        if self.settings:
            self.settings.set_int(key, value)

    def set_bool(self, key: str, value: bool) -> None:
        if self.settings:
            self.settings.set_boolean(key, value)

    def set_string(self, key: str, value: str) -> None:
        if self.settings:
            self.settings.set_string(key, value)
