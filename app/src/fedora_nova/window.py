from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .backend import Backend, CommandResult
from .constants import APP_NAME
from .pages import Pages
from .state import WindowState


class NovaWindow(Adw.ApplicationWindow):
    PAGE_INFO = [
        ("appearance", "Vzhled", "applications-graphics-symbolic"),
        ("colors", "Barvy", "color-select-symbolic"),
        ("monitors", "Monitory", "video-display-symbolic"),
        ("system", "Systém", "preferences-system-symbolic"),
    ]

    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application)
        self.backend = Backend()
        self.profile_css_provider = Gtk.CssProvider()
        self._install_profile_css()
        self.state = WindowState()
        self.pages_factory = Pages(self, self.backend)
        self.current_page = self.state.get_string("last-page", "appearance")

        self.set_title(APP_NAME)
        self.set_default_size(
            self.state.get_int("window-width", 1040),
            self.state.get_int("window-height", 720),
        )
        self.set_size_request(360, 460)
        if self.state.get_bool("window-maximized", False):
            self.maximize()

        self.toast_overlay = Adw.ToastOverlay()
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)

        self._build_pages()
        self.sidebar_list = self._build_sidebar()

        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        self.sidebar_title = Adw.WindowTitle(
            title="Fedora Nova",
            subtitle=self.backend.mode_label,
        )
        sidebar_header.set_title_widget(self.sidebar_title)
        sidebar_toolbar.add_top_bar(sidebar_header)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        sidebar_scroll.set_child(self.sidebar_list)
        sidebar_toolbar.set_content(sidebar_scroll)

        content_toolbar = Adw.ToolbarView()
        self.content_header = Adw.HeaderBar()
        self.content_header.pack_end(self.spinner)
        self.content_header.pack_end(self._menu_button())
        content_toolbar.add_top_bar(self.content_header)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.backend_banner = Adw.Banner()
        self.backend_banner.set_revealed(True)
        content_box.append(self.backend_banner)
        content_box.append(self.stack)
        content_toolbar.set_content(content_box)

        sidebar_page = Adw.NavigationPage(
            title="Fedora Nova",
            tag="sidebar",
            child=sidebar_toolbar,
        )
        self.content_page = Adw.NavigationPage(
            title="Vzhled",
            tag="content",
            child=content_toolbar,
        )

        self.split_view = Adw.NavigationSplitView(
            sidebar=sidebar_page,
            content=self.content_page,
        )
        self.split_view.set_min_sidebar_width(210)
        self.split_view.set_max_sidebar_width(285)
        self.split_view.set_sidebar_width_fraction(0.24)

        self.toast_overlay.set_child(self.split_view)
        self.set_content(self.toast_overlay)

        condition = Adw.BreakpointCondition.parse("max-width: 720sp")
        breakpoint = Adw.Breakpoint.new(condition)
        breakpoint.add_setter(self.split_view, "collapsed", True)
        self.add_breakpoint(breakpoint)

        self.connect("close-request", self._on_close_request)
        self._update_backend_chrome()
        self._select_page(self.current_page, navigate=False)
        GLib.idle_add(self._initial_navigation_state)

    def _build_pages(self) -> None:
        for child in list(self._stack_children()):
            self.stack.remove(child)
        pages = {
            "appearance": self.pages_factory.appearance(),
            "colors": self.pages_factory.colors(),
            "monitors": self.pages_factory.monitors(),
            "system": self.pages_factory.system(),
        }
        for name, title, icon in self.PAGE_INFO:
            self.stack.add_titled(pages[name], name, title)
            page = self.stack.get_page(pages[name])
            page.set_icon_name(icon)

    def _stack_children(self):
        child = self.stack.get_first_child()
        while child is not None:
            yield child
            child = child.get_next_sibling()

    def _build_sidebar(self) -> Gtk.ListBox:
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.add_css_class("navigation-sidebar")
        listbox.set_margin_top(8)
        listbox.set_margin_bottom(8)
        listbox.set_margin_start(8)
        listbox.set_margin_end(8)

        for name, title, icon_name in self.PAGE_INFO:
            row = Gtk.ListBoxRow()
            row.page_name = name
            box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=12,
            )
            box.set_margin_top(10)
            box.set_margin_bottom(10)
            box.set_margin_start(12)
            box.set_margin_end(12)
            image = Gtk.Image.new_from_icon_name(icon_name)
            label = Gtk.Label(label=title, xalign=0)
            label.set_hexpand(True)
            box.append(image)
            box.append(label)
            row.set_child(box)
            listbox.append(row)

        listbox.connect("row-activated", self._on_sidebar_activated)
        return listbox

    def _menu_button(self) -> Gtk.MenuButton:
        menu = Gio.Menu()
        menu.append("Obnovit obsah", "win.refresh")
        menu.append("Adaptive Preview", "win.adaptive")
        menu.append("O aplikaci", "app.about")

        button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        button.set_menu_model(menu)
        return button

    def _install_profile_css(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        Gtk.StyleContext.add_provider_for_display(
            display,
            self.profile_css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )
        self._reload_profile_css()

    def _css_color(
        self,
        data: dict[str, object],
        key: str,
        fallback: str,
    ) -> str:
        value = str(data.get(key, fallback))
        rgba = Gdk.RGBA()
        return value if rgba.parse(value) else fallback

    def _reload_profile_css(self) -> None:
        data = self.backend.profile_data()
        colors = {
            "bg": self._css_color(data, "bg", "#08091B"),
            "panel": self._css_color(data, "panel", "#050817"),
            "large": self._css_color(data, "large", "#120C25"),
            "surface": self._css_color(data, "surface", "#21133A"),
            "surface2": self._css_color(data, "surface2", "#2B1749"),
            "card": self._css_color(data, "card", "#2A1C3D"),
            "accent": self._css_color(data, "accent", "#2ED8E8"),
            "accent_bright": self._css_color(data, "accent_bright", "#6FE7F7"),
            "accent_fg": self._css_color(data, "accent_fg", "#06131A"),
            "secondary": self._css_color(data, "secondary", "#8C5CFF"),
            "text": self._css_color(data, "text", "#F8EFFF"),
            "muted": self._css_color(data, "muted", "#B5A2C4"),
            "border": self._css_color(data, "border", "#60406E"),
        }
        css = "\n".join(
            [
                f"@define-color nova_{name} {value};"
                for name, value in colors.items()
            ]
            + [
                f"@define-color accent_color {colors['accent']};",
                f"@define-color accent_bg_color {colors['accent']};",
                f"@define-color accent_fg_color {colors['accent_fg']};",
                f"@define-color window_bg_color {colors['bg']};",
                f"@define-color window_fg_color {colors['text']};",
                f"@define-color view_bg_color {colors['large']};",
                f"@define-color view_fg_color {colors['text']};",
                f"@define-color card_bg_color {colors['card']};",
                f"@define-color card_fg_color {colors['text']};",
                f"@define-color headerbar_bg_color {colors['panel']};",
                f"@define-color headerbar_fg_color {colors['text']};",
                f"@define-color sidebar_bg_color {colors['panel']};",
                f"@define-color sidebar_fg_color {colors['text']};",
            ]
        )
        try:
            self.profile_css_provider.load_from_data(css.encode("utf-8"))
        except TypeError:
            self.profile_css_provider.load_from_data(css)

    def _initial_navigation_state(self) -> bool:
        if self.split_view.get_collapsed():
            self.split_view.set_show_content(False)
        return GLib.SOURCE_REMOVE

    def _on_sidebar_activated(
        self,
        _listbox: Gtk.ListBox,
        row: Gtk.ListBoxRow,
    ) -> None:
        self._select_page(row.page_name, navigate=True)

    def _select_page(self, name: str, navigate: bool) -> None:
        valid = {item[0]: item[1] for item in self.PAGE_INFO}
        if name not in valid:
            name = "appearance"
        self.current_page = name
        self.stack.set_visible_child_name(name)
        self.content_page.set_title(valid[name])
        self.state.set_string("last-page", name)

        child = self.sidebar_list.get_first_child()
        while child is not None:
            if getattr(child, "page_name", "") == name:
                self.sidebar_list.select_row(child)
                break
            child = child.get_next_sibling()

        if navigate and self.split_view.get_collapsed():
            self.split_view.set_show_content(True)

    def toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)

    def _set_busy(self, busy: bool) -> None:
        self.spinner.set_visible(busy)
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()

    def run_async(
        self,
        args: list[str],
        success: str,
        callback: Callable[[CommandResult], None] | None = None,
    ) -> None:
        self._set_busy(True)

        def worker() -> None:
            result = self.backend.run(*args)
            GLib.idle_add(self._command_finished, result, success, callback)

        threading.Thread(target=worker, daemon=True).start()

    def _command_finished(
        self,
        result: CommandResult,
        success: str,
        callback: Callable[[CommandResult], None] | None,
    ) -> bool:
        self._set_busy(False)
        self.toast(success if result.ok else result.message)
        if callback is not None:
            callback(result)
        return GLib.SOURCE_REMOVE

    def run_output_dialog(self, title: str, args: list[str]) -> None:
        def show(result: CommandResult) -> None:
            output = (result.stdout + "\n" + result.stderr).strip() or "Hotovo."
            dialog = Adw.MessageDialog.new(self, title, output[-8000:])
            dialog.add_response("close", "Zavřít")
            dialog.set_default_response("close")
            dialog.present()

        self.run_async(args, "Příkaz dokončen", show)

    def spawn_external(self, command: list[str]) -> None:
        if self.backend.preview:
            self.toast("V Preview režimu se externí systémové okno neotevírá.")
            return
        try:
            subprocess.Popen(command)
        except OSError as exc:
            self.toast(str(exc))

    def _update_backend_chrome(self) -> None:
        self.sidebar_title.set_subtitle(self.backend.mode_label)
        if self.backend.preview:
            self.backend_banner.set_title(
                "PREVIEW: ovládání je interaktivní, ale hostitelský systém se nemění."
            )
            self.backend_banner.remove_css_class("system-host-banner")
        else:
            self.backend_banner.set_title(
                "SYSTEM HOST: změny se aplikují do skutečného GNOME na této Fedoře."
            )
            self.backend_banner.add_css_class("system-host-banner")

    def switch_backend(self, mode: str) -> None:
        result = self.backend.set_runtime_mode(mode)
        if not result.ok:
            self.toast(result.message)
            return
        self._reload_profile_css()
        self._update_backend_chrome()
        self.refresh_pages()
        self.toast(f"Backend: {self.backend.mode_label}")

    def refresh_pages(self, show_toast: bool = True) -> None:
        current = self.current_page
        self.pages_factory = Pages(self, self.backend)
        self._build_pages()
        self._select_page(current, navigate=False)
        if show_toast:
            self.toast("Obsah byl obnoven")

    def profile_changed(self, result: CommandResult) -> None:
        if not result.ok:
            return
        self._reload_profile_css()
        self.refresh_pages(show_toast=False)

    def toggle_adaptive_preview(self) -> None:
        if not hasattr(self, "get_adaptive_preview"):
            self.toast("Tato verze libadwaita Adaptive Preview nepodporuje.")
            return
        self.set_adaptive_preview(not self.get_adaptive_preview())

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        maximized = self.is_maximized()
        if not maximized:
            self.state.set_int("window-width", self.get_width())
            self.state.set_int("window-height", self.get_height())
        self.state.set_bool("window-maximized", maximized)
        self.state.set_string("last-page", self.current_page)
        return False
