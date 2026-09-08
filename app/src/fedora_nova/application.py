from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from .constants import (
    APP_ID,
    APP_NAME,
    ISSUE_URL,
    PROJECT_URL,
    STYLE_PATH,
    VERSION,
)
from .window import NovaWindow


class NovaApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.window: NovaWindow | None = None
        self._install_actions()
        self._configure_style()
        self._load_css()

    def _install_actions(self) -> None:
        for name, callback in [
            ("about", self._about),
            ("quit", lambda *_args: self.quit()),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.set_accels_for_action("app.quit", ["<primary>q"])

    def _configure_style(self) -> None:
        if os.environ.get("FEDORA_NOVA_PREVIEW") != "1" and not os.path.exists(
            "/.flatpak-info"
        ):
            return
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def _load_css(self) -> None:
        if not STYLE_PATH.is_file():
            return
        display = Gdk.Display.get_default()
        if display is None:
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(STYLE_PATH))
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def do_activate(self) -> None:
        if self.window is None:
            self.window = NovaWindow(self)
            self._install_window_actions(self.window)
        self.window.present()

    def _install_window_actions(self, window: NovaWindow) -> None:
        refresh = Gio.SimpleAction.new("refresh", None)
        refresh.connect("activate", lambda *_args: window.refresh_pages())
        window.add_action(refresh)

        adaptive = Gio.SimpleAction.new("adaptive", None)
        adaptive.connect(
            "activate",
            lambda *_args: window.toggle_adaptive_preview(),
        )
        window.add_action(adaptive)

        self.set_accels_for_action("win.refresh", ["<primary>r"])
        self.set_accels_for_action("win.adaptive", ["<primary><shift>m"])

    def _about(self, *_args: object) -> None:
        about = Adw.AboutWindow(
            transient_for=self.window,
            application_name=APP_NAME,
            application_icon=APP_ID,
            developer_name="Fedora Nova contributors",
            version=VERSION,
            license_type=Gtk.License.GPL_3_0,
            website=PROJECT_URL,
            issue_url=ISSUE_URL,
            developers=["Marek Suranič", "Fedora Nova contributors"],
            comments=(
                "Builder-ready responsive development application "
                "for Fedora Nova."
            ),
        )
        about.present()


def main() -> int:
    Adw.init()
    return NovaApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
