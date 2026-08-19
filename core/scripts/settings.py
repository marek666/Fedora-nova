#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "nova"
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
NOVA_CONFIG = CONFIG_HOME / "fedora-nova"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
UUID = "topbar-all-monitors@fa8i.github.io"


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), *args],
        text=True,
        capture_output=True,
        check=check,
    )


def read_state(name: str, default: str) -> str:
    file = NOVA_CONFIG / name
    try:
        value = file.read_text(encoding="utf-8").strip()
        return value or default
    except OSError:
        return default


def list_profiles() -> list[tuple[str, str]]:
    proc = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/profile-info.py"),
            "list",
            str(ROOT / "config/profiles.json"),
            str(NOVA_CONFIG / "custom-profiles"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    rows: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            profile_id, title, description, kind = parts[:4]
            suffix = " · Forge" if kind == "custom" else ""
            rows.append((profile_id, f"{title}{suffix} — {description}"))
    return rows


def list_curves() -> list[tuple[str, str]]:
    data = json.loads((ROOT / "config/curves.json").read_text(encoding="utf-8"))
    return [
        (key, f"{value['title']} — {value['description']}")
        for key, value in data["presets"].items()
    ]


def monitor_enabled() -> bool:
    proc = run_cli("monitors", "status", check=False)
    return "Enabled:    yes" in proc.stdout or "Enabled:    pending-or-enabled" in proc.stdout


def current_profile_data() -> dict[str, object]:
    profile = read_state("current-profile", "tech")
    proc = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/profile-info.py"),
            "json",
            profile,
            str(ROOT / "config/profiles.json"),
            str(NOVA_CONFIG / "custom-profiles"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


class NovaSettings(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.fedora_nova.Settings")
        self.window: Adw.ApplicationWindow | None = None
        self.toasts: Adw.ToastOverlay | None = None

    def do_activate(self) -> None:
        if self.window is not None:
            self.window.present()
            return

        self.window = Adw.ApplicationWindow(application=self)
        self.window.set_title("Fedora Nova Settings")
        self.window.set_default_size(940, 680)

        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(
                title="Fedora Nova Settings",
                subtitle="0.6.4 · Dock hover · Large icon halo",
            )
        )

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.set_hexpand(True)
        stack.set_vexpand(True)

        stack.add_titled(self.appearance_page(), "appearance", "Vzhled")
        stack.add_titled(self.colors_page(), "colors", "Barvy")
        stack.add_titled(self.monitors_page(), "monitors", "Monitory")
        stack.add_titled(self.system_page(), "system", "Systém")

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(stack)
        sidebar.set_size_request(230, -1)

        split = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        split.set_start_child(sidebar)
        split.set_end_child(stack)
        split.set_resize_start_child(False)
        split.set_shrink_start_child(False)
        split.set_position(245)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(split)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(toolbar)
        self.window.set_content(self.toasts)
        self.window.present()

    def toast(self, message: str) -> None:
        if self.toasts is not None:
            toast = Adw.Toast.new(message)
            toast.set_timeout(4)
            self.toasts.add_toast(toast)

    def run_and_toast(self, args: list[str], success: str) -> None:
        proc = run_cli(*args, check=False)
        if proc.returncode == 0:
            self.toast(success)
        else:
            error = (proc.stderr or proc.stdout).strip().splitlines()
            self.toast(error[-1] if error else "Příkaz selhal")

    @staticmethod
    def dropdown_row(title: str, items: list[tuple[str, str]], current: str) -> tuple[Adw.ActionRow, Gtk.DropDown, list[str]]:
        ids = [item[0] for item in items]
        labels = [item[1] for item in items]
        row = Adw.ActionRow(title=title)
        dropdown = Gtk.DropDown.new_from_strings(labels)
        dropdown.set_valign(Gtk.Align.CENTER)
        if current in ids:
            dropdown.set_selected(ids.index(current))
        row.add_suffix(dropdown)
        row.set_activatable_widget(dropdown)
        return row, dropdown, ids

    def appearance_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Vzhled",
            icon_name="applications-graphics-symbolic",
        )

        profiles = list_profiles()
        profile_group = Adw.PreferencesGroup(
            title="Fedora Nova profil",
            description="Vestavěné i vlastní Forge profily.",
        )
        profile_row, profile_dropdown, profile_ids = self.dropdown_row(
            "Aktivní profil", profiles, read_state("current-profile", "tech")
        )
        profile_group.add(profile_row)
        apply_profile = Gtk.Button(label="Použít profil")
        apply_profile.add_css_class("suggested-action")
        apply_profile.set_halign(Gtk.Align.END)
        apply_profile.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["profile", profile_ids[profile_dropdown.get_selected()], "--reload"],
                "Profil byl použit",
            ),
        )
        profile_group.add(self.button_row("", apply_profile))
        page.add(profile_group)

        curve_group = Adw.PreferencesGroup(
            title="Continuous Curve",
            description="Společný poměr vnějších a vnitřních rohů.",
        )
        curves = list_curves()
        curve_row, curve_dropdown, curve_ids = self.dropdown_row(
            "Charakter rohů", curves, read_state("current-curve", "squircle")
        )
        curve_group.add(curve_row)
        apply_curve = Gtk.Button(label="Použít křivky")
        apply_curve.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["curve", curve_ids[curve_dropdown.get_selected()], "--reload"],
                "Křivky byly použity",
            ),
        )
        curve_group.add(self.button_row("", apply_curve))
        page.add(curve_group)

        hover_group = Adw.PreferencesGroup(
            title="Hover ikon",
            description=(
                "Circle Large používá větší halo bez změny geometrie. "
                "Folder má vždy jen jednu zvýrazněnou vrstvu."
            ),
        )
        hover_items = [
            ("circle", "Circle Large — větší kruh pouze pod ikonou"),
            ("circle-compact", "Circle Compact — menší kruhový hover"),
            ("tile", "Tile — barevný squircle kolem celé dlaždice"),
            ("none", "None — bez hover podložky"),
        ]
        hover_row, hover_dropdown, hover_ids = self.dropdown_row(
            "Styl hoveru", hover_items, read_state("current-hover", "circle")
        )
        hover_group.add(hover_row)
        apply_hover = Gtk.Button(label="Použít hover")
        apply_hover.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["hover", hover_ids[hover_dropdown.get_selected()], "--reload"],
                "Hover ikon byl změněn",
            ),
        )
        hover_group.add(self.button_row("", apply_hover))
        page.add(hover_group)

        icons = [
            ("tela", "Tela Circle"),
            ("tela-dark", "Tela Circle Dark"),
            ("tela-light", "Tela Circle Light"),
            ("tela-steam", "Tela Circle + kruhové Steam hry"),
            ("papirus", "Papirus Dark"),
            ("adwaita", "Adwaita"),
        ]
        icon_group = Adw.PreferencesGroup(
            title="Ikony",
            description="Tela Circle je výchozí sada Fedora Nova 0.6.",
        )
        icon_row, icon_dropdown, icon_ids = self.dropdown_row(
            "Sada ikon", icons, read_state("current-icons", "tela")
        )
        icon_group.add(icon_row)
        apply_icons = Gtk.Button(label="Použít ikony")
        apply_icons.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["icons", icon_ids[icon_dropdown.get_selected()]],
                "Ikony byly změněny",
            ),
        )
        icon_group.add(self.button_row("", apply_icons))
        steam_button = Gtk.Button(label="Zaoblit ikony Steam her")
        steam_button.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["steam-icons", "round"],
                "Steam ikony byly zpracovány; může být potřeba znovu otevřít Přehled",
            ),
        )
        icon_group.add(self.button_row("Steam hry", steam_button))
        restore_steam = Gtk.Button(label="Obnovit původní Steam ikony")
        restore_steam.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["steam-icons", "restore"],
                "Původní icon theme byl obnoven",
            ),
        )
        icon_group.add(self.button_row("Návrat", restore_steam))
        page.add(icon_group)

        forge_group = Adw.PreferencesGroup(
            title="Nova Forge",
            description="Nový profil z jedné nebo dvou HEX barev.",
        )
        name_row = Adw.EntryRow(title="Název profilu")
        name_row.set_text("My Nova")
        primary_row = Adw.EntryRow(title="Hlavní barva")
        primary_row.set_text("#D630F2")
        secondary_row = Adw.EntryRow(title="Vedlejší barva")
        secondary_row.set_text("#2ED8E8")
        forge_group.add(name_row)
        forge_group.add(primary_row)
        forge_group.add(secondary_row)
        forge_button = Gtk.Button(label="Vytvořit a použít")
        forge_button.add_css_class("suggested-action")

        def forge_profile(_button: Gtk.Button) -> None:
            args = ["forge", name_row.get_text(), primary_row.get_text()]
            if secondary_row.get_text().strip():
                args.append(secondary_row.get_text())
            self.run_and_toast(args, "Forge profil byl vytvořen")

        forge_button.connect("clicked", forge_profile)
        forge_group.add(self.button_row("", forge_button))
        page.add(forge_group)
        return page

    def colors_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Barvy", icon_name="color-select-symbolic")
        data = current_profile_data()

        theme_group = Adw.PreferencesGroup(
            title="Barvy theme",
            description="Designové barvy Fedora Nova; nemění kalibraci monitoru.",
        )
        for title, key in [
            ("Hlavní akcent", "accent"),
            ("Vedlejší akcent", "secondary"),
            ("Panel", "panel"),
            ("Velké plochy", "large"),
            ("Text", "text"),
        ]:
            theme_group.add(
                Adw.ActionRow(title=title, subtitle=str(data.get(key, "—")))
            )
        page.add(theme_group)

        gtk_group = Adw.PreferencesGroup(
            title="Vzhled GTK/libadwaita aplikací",
            description=(
                "Přebarví Soubory, Textový editor, Nastavení a další GTK aplikace "
                "podle aktivního Nova profilu. Běžící aplikace je nutné znovu otevřít."
            ),
        )
        gtk_switch = Adw.SwitchRow(
            title="Nova barvy v aplikacích",
            subtitle="Bez zásahu do Vivaldi, Steamu a aplikací s vlastním UI",
        )
        gtk_switch.set_active(read_state("current-gtk", "on") == "on")

        def toggle_gtk(row: Adw.SwitchRow, _pspec: object) -> None:
            command = "on" if row.get_active() else "off"
            self.run_and_toast(
                ["gtk", command],
                "GTK vrstva byla změněna; aplikace znovu otevři",
            )

        gtk_switch.connect("notify::active", toggle_gtk)
        gtk_group.add(gtk_switch)
        refresh_gtk = Gtk.Button(label="Aktualizovat podle profilu")
        refresh_gtk.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["gtk", "refresh"],
                "Barvy aplikací byly aktualizovány",
            ),
        )
        gtk_group.add(self.button_row("Aktivní profil", refresh_gtk))
        page.add(gtk_group)

        display_group = Adw.PreferencesGroup(
            title="ICC profily monitorů",
            description=(
                "Každý monitor má vlastní zařízení a výchozí ICC profil. "
                "Tohle je oddělené od barev theme."
            ),
        )
        color_button = Gtk.Button(label="Otevřít Nastavení → Barva")
        color_button.connect(
            "clicked",
            lambda _button: self.spawn_external(["gnome-control-center", "color"]),
        )
        display_group.add(self.button_row("Kalibrace a ICC profily", color_button))
        display_button = Gtk.Button(label="Otevřít rozložení displejů")
        display_button.connect(
            "clicked",
            lambda _button: self.spawn_external(["gnome-control-center", "display"]),
        )
        display_group.add(self.button_row("Rozlišení, měřítko a primární monitor", display_button))
        page.add(display_group)
        return page

    def monitors_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Monitory", icon_name="video-display-symbolic")
        group = Adw.PreferencesGroup(
            title="Horní panel na všech monitorech",
            description=(
                "Top Bar All Monitors přidává skutečný GNOME panel na každý "
                "sekundární monitor. Určeno pro GNOME 50 a Wayland."
            ),
        )
        switch = Adw.SwitchRow(
            title="Panel na sekundárních monitorech",
            subtitle="Activities, hodiny, kalendář a Quick Settings",
        )
        switch.set_active(monitor_enabled())

        def toggle_monitor(row: Adw.SwitchRow, _pspec: object) -> None:
            command = "on" if row.get_active() else "off"
            self.run_and_toast(
                ["monitors", command],
                "Nastavení panelů bylo změněno; může být nutný relogin",
            )

        switch.connect("notify::active", toggle_monitor)
        group.add(switch)
        refresh = Gtk.Button(label="Obnovit bundled extension")
        refresh.connect(
            "clicked",
            lambda _button: self.run_and_toast(
                ["monitors", "refresh"],
                "Rozšíření bylo obnoveno; proveď relogin",
            ),
        )
        group.add(self.button_row("Přepsat lokální kopii upstream verzí z balíku", refresh))
        page.add(group)
        return page

    def system_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Systém", icon_name="preferences-system-symbolic")

        tools = Adw.PreferencesGroup(title="Údržba")
        for title, label, args in [
            ("Stav Fedora Nova", "Zobrazit stav", ["status"]),
            ("Diagnostika", "Spustit doctor", ["doctor"]),
            ("Snapshot", "Vytvořit snapshot", ["snapshot", "create"]),
            ("Nouzový režim", "Vypnout theme a dock", ["safe-mode"]),
        ]:
            button = Gtk.Button(label=label)
            if args == ["safe-mode"]:
                button.add_css_class("destructive-action")
            button.connect(
                "clicked",
                lambda _button, command=args, name=title: self.command_dialog(name, command),
            )
            tools.add(self.button_row(title, button))
        page.add(tools)
        return page

    @staticmethod
    def button_row(title: str, button: Gtk.Button) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        button.set_valign(Gtk.Align.CENTER)
        row.add_suffix(button)
        row.set_activatable_widget(button)
        return row

    def spawn_external(self, command: list[str]) -> None:
        try:
            subprocess.Popen(command)
        except OSError as exc:
            self.toast(str(exc))

    def command_dialog(self, title: str, args: list[str]) -> None:
        proc = run_cli(*args, check=False)
        output = (proc.stdout + "\n" + proc.stderr).strip() or "Hotovo."
        dialog = Adw.MessageDialog.new(self.window, title, output[-5000:])
        dialog.add_response("close", "Zavřít")
        dialog.set_default_response("close")
        dialog.present()


def main() -> int:
    Adw.init()
    return NovaSettings().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
