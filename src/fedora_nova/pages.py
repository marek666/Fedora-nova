from __future__ import annotations

from typing import TYPE_CHECKING
import threading

from gi.repository import Adw, GLib, Gtk

from .backend import Backend
from .widgets import (
    button_row,
    color_row,
    combo_row,
    desktop_preview,
    selected_id,
)

if TYPE_CHECKING:
    from .window import NovaWindow


class Pages:
    def __init__(self, window: NovaWindow, backend: Backend) -> None:
        self.window = window
        self.backend = backend

    def appearance(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Vzhled",
            description="Profily, křivky, hover, ikony a Nova Forge.",
            icon_name="applications-graphics-symbolic",
        )
        data = self.backend.profile_data()

        preview_group = Adw.PreferencesGroup(title="Aktivní vzhled")
        wallpaper = self.backend.core_root / "assets/wallpapers" / str(
            data.get("wallpaper", "fedora-nova-flow.svg")
        )
        preview_group.add(desktop_preview(data, wallpaper))
        page.add(preview_group)

        profile_group = Adw.PreferencesGroup(
            title="Fedora Nova profil",
            description="Vestavěné a vlastní Forge profily.",
        )
        profile_row, profile_ids = combo_row(
            "Aktivní profil",
            self.backend.profiles(),
            self.backend.read_state("current-profile", "tech"),
            fallback="tech",
        )
        profile_group.add(profile_row)
        profile_button = Gtk.Button(label="Použít profil")
        profile_button.add_css_class("suggested-action")
        profile_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                [
                    "profile",
                    selected_id(profile_row, profile_ids, "tech"),
                    "--reload",
                ],
                "Profil byl použit",
                self.window.profile_changed,
            ),
        )
        profile_group.add(button_row("", profile_button))
        page.add(profile_group)

        curve_group = Adw.PreferencesGroup(
            title="Continuous Curve",
            description="Společný poměr vnějších a vnitřních rohů.",
        )
        curve_row, curve_ids = combo_row(
            "Charakter rohů",
            self.backend.curves(),
            self.backend.read_state("current-curve", "squircle"),
            fallback="squircle",
        )
        curve_group.add(curve_row)
        curve_button = Gtk.Button(label="Použít křivky")
        curve_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["curve", selected_id(curve_row, curve_ids, "squircle"), "--reload"],
                "Křivky byly použity",
            ),
        )
        curve_group.add(button_row("", curve_button))
        page.add(curve_group)

        hover_items = [
            ("circle", "Circle Large — větší kruh pouze pod ikonou"),
            ("circle-compact", "Circle Compact — menší kruhový hover"),
            ("tile", "Tile — squircle kolem celé dlaždice"),
            ("none", "None — bez hover podložky"),
        ]
        hover_group = Adw.PreferencesGroup(
            title="Hover ikon",
            description="Halo nemění padding ani velikost ikony.",
        )
        hover_row, hover_ids = combo_row(
            "Styl hoveru",
            hover_items,
            self.backend.read_state("current-hover", "circle"),
            fallback="circle",
        )
        hover_group.add(hover_row)
        hover_button = Gtk.Button(label="Použít hover")
        hover_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["hover", selected_id(hover_row, hover_ids, "circle"), "--reload"],
                "Hover byl změněn",
            ),
        )
        hover_group.add(button_row("", hover_button))
        page.add(hover_group)

        icon_items = [
            ("tela", "Tela Circle"),
            ("tela-dark", "Tela Circle Dark"),
            ("tela-light", "Tela Circle Light"),
            ("tela-steam", "Tela Circle + kruhové Steam hry"),
            ("papirus", "Papirus Dark"),
            ("adwaita", "Adwaita"),
        ]
        icon_group = Adw.PreferencesGroup(
            title="Ikony",
            description="Systémová sada a zpracování vlastních Steam launcherů.",
        )
        icon_row, icon_ids = combo_row(
            "Sada ikon",
            icon_items,
            self.backend.read_state("current-icons", "tela"),
            fallback="tela",
        )
        icon_group.add(icon_row)
        icon_button = Gtk.Button(label="Použít ikony")
        icon_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["icons", selected_id(icon_row, icon_ids, "tela")],
                "Ikony byly změněny",
            ),
        )
        icon_group.add(button_row("", icon_button))

        round_button = Gtk.Button(label="Zaoblit Steam ikony")
        round_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["steam-icons", "round"],
                "Steam ikony byly zpracovány",
            ),
        )
        icon_group.add(button_row("Steam hry", round_button))

        restore_button = Gtk.Button(label="Obnovit původní ikony")
        restore_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["steam-icons", "restore"],
                "Původní Steam ikony byly obnoveny",
            ),
        )
        icon_group.add(button_row("Návrat", restore_button))
        page.add(icon_group)

        forge_group = Adw.PreferencesGroup(
            title="Nova Forge",
            description="Vytvoří profil z jedné nebo dvou HEX barev.",
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

        def create_forge(_button: Gtk.Button) -> None:
            args = ["forge", name_row.get_text(), primary_row.get_text()]
            if secondary_row.get_text().strip():
                args.append(secondary_row.get_text())
            self.window.run_async(
                args,
                "Forge profil byl vytvořen",
                self.window.profile_changed,
            )

        forge_button.connect("clicked", create_forge)
        forge_group.add(button_row("", forge_button))
        page.add(forge_group)
        return page

    def colors(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Barvy",
            description="Theme barvy a skutečné ICC profily monitorů.",
            icon_name="color-select-symbolic",
        )
        data = self.backend.profile_data()

        theme_group = Adw.PreferencesGroup(
            title="Barvy aktivního profilu",
            description="Tyto barvy mění design, nikoliv kalibraci monitoru.",
        )
        for title, key in [
            ("Hlavní akcent", "accent"),
            ("Vedlejší akcent", "secondary"),
            ("Panel", "panel"),
            ("Velké plochy", "large"),
            ("Text", "text"),
        ]:
            theme_group.add(color_row(title, str(data.get(key, "#777777"))))
        page.add(theme_group)

        gtk_group = Adw.PreferencesGroup(
            title="GTK a libadwaita aplikace",
            description=(
                "Přebarví Soubory, Textový editor, Nastavení a další "
                "kompatibilní aplikace."
            ),
        )
        gtk_switch = Adw.SwitchRow(
            title="Nova barvy v aplikacích",
            subtitle="Běžící aplikace je po změně nutné znovu otevřít.",
        )
        gtk_switch.set_active(
            self.backend.read_state("current-gtk", "on") == "on"
        )

        def toggle_gtk(row: Adw.SwitchRow, _pspec: object) -> None:
            value = "on" if row.get_active() else "off"
            self.window.run_async(
                ["gtk", value],
                "GTK vrstva byla změněna",
            )

        gtk_switch.connect("notify::active", toggle_gtk)
        gtk_group.add(gtk_switch)

        refresh = Gtk.Button(label="Aktualizovat podle profilu")
        refresh.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["gtk", "refresh"],
                "Barvy aplikací byly aktualizovány",
            ),
        )
        gtk_group.add(button_row("Aktivní profil", refresh))
        page.add(gtk_group)

        display_group = Adw.PreferencesGroup(
            title="ICC profily monitorů",
            description=(
                "Kalibrace obrazu je oddělená od Fedora Nova theme a "
                "spravuje se pro každý monitor samostatně."
            ),
        )
        colors_button = Gtk.Button(label="Otevřít Nastavení → Barva")
        colors_button.connect(
            "clicked",
            lambda _button: self.window.spawn_external(
                ["gnome-control-center", "color"]
            ),
        )
        display_group.add(button_row("Kalibrace a ICC", colors_button))

        displays_button = Gtk.Button(label="Otevřít rozložení displejů")
        displays_button.connect(
            "clicked",
            lambda _button: self.window.spawn_external(
                ["gnome-control-center", "display"]
            ),
        )
        display_group.add(button_row("Rozlišení a měřítko", displays_button))
        page.add(display_group)
        return page

    def monitors(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Monitory",
            description="Panely a pomocné nástroje pro více monitorů.",
            icon_name="video-display-symbolic",
        )
        group = Adw.PreferencesGroup(
            title="Horní panel na všech monitorech",
            description=(
                "Top Bar All Monitors přidá GNOME panel na sekundární monitor."
            ),
        )
        switch = Adw.SwitchRow(
            title="Panel na sekundárních monitorech",
            subtitle="Activities, hodiny, kalendář a Quick Settings.",
        )
        switch.set_active(self.backend.monitor_enabled())

        def toggle(row: Adw.SwitchRow, _pspec: object) -> None:
            command = "on" if row.get_active() else "off"
            self.window.run_async(
                ["monitors", command],
                "Nastavení panelů bylo změněno",
            )

        switch.connect("notify::active", toggle)
        group.add(switch)

        refresh = Gtk.Button(label="Obnovit bundled extension")
        refresh.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["monitors", "refresh"],
                "Rozšíření bylo obnoveno; může být nutný relogin",
            ),
        )
        group.add(button_row("Lokální kopie rozšíření", refresh))
        page.add(group)
        return page

    def system(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Systém",
            description="Diagnostika, snapshoty a vývojové informace.",
            icon_name="preferences-system-symbolic",
        )

        backend_group = Adw.PreferencesGroup(
            title="Vývojový backend",
            description=(
                "Preview je bezpečný sandbox. System Host spouští skutečné "
                "Fedora Nova CLI na hostitelské Fedoře."
            ),
        )
        host_switch = Adw.SwitchRow(
            title="System Host",
            subtitle=(
                "Zapnuté = tlačítka mění skutečný GNOME systém. "
                "Ve Flatpaku se používá flatpak-spawn --host."
            ),
        )
        host_switch.set_active(self.backend.runtime_mode == "host")
        host_switch.set_sensitive(self.backend.can_host)

        def toggle_backend(row: Adw.SwitchRow, _pspec: object) -> None:
            mode = "host" if row.get_active() else "preview"
            self.window.switch_backend(mode)

        host_switch.connect("notify::active", toggle_backend)
        backend_group.add(host_switch)
        backend_group.add(
            Adw.ActionRow(
                title="Aktivní režim",
                subtitle=self.backend.mode_label,
            )
        )
        backend_group.add(
            Adw.ActionRow(
                title="Core projektu",
                subtitle=str(self.backend.core_root),
            )
        )
        page.add(backend_group)

        preset_group = Adw.PreferencesGroup(
            title="Kompletní Nova setup",
            description=(
                "Aktivní profil, rozšíření, křivky, hover, ikony, Steam a "
                "GTK barvy jedním krokem."
            ),
        )
        full_button = Gtk.Button(label="Použít a zapamatovat")
        full_button.add_css_class("suggested-action")
        full_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["preset", "full", "--reload"],
                "Kompletní Nova setup byl použit",
                self.window.profile_changed,
            ),
        )
        preset_group.add(button_row("Persistentní nastavení", full_button))
        restore_button = Gtk.Button(label="Obnovit po přihlášení")
        restore_button.connect(
            "clicked",
            lambda _button: self.window.run_async(
                ["session-restore", "apply"],
                "Nova setup byl znovu aplikován",
                self.window.profile_changed,
            ),
        )
        preset_group.add(button_row("Aktuální session", restore_button))
        page.add(preset_group)

        shell_group = Adw.PreferencesGroup(
            title="GNOME Shell Preview",
            description=(
                "Spustí skutečný izolovaný GNOME Shell v okně přes "
                "Mutter Development Kit. Theme a dconf preview jsou oddělené "
                "od normálního desktopu."
            ),
        )
        current_shell_profile = self.backend.read_state("current-profile", "tech")
        if current_shell_profile == "system":
            current_shell_profile = "tech"

        shell_profiles = [
            item for item in self.backend.profiles()
            if item[0] != "system" and not item[0].startswith("custom-")
        ]

        shell_profile_row, shell_profile_ids = combo_row(
            "Profil v testovacím Shellu",
            shell_profiles,
            current_shell_profile,
            fallback="tech",
        )
        shell_group.add(shell_profile_row)

        shell_button = Gtk.Button(label="Spustit Shell Preview")
        shell_button.add_css_class("suggested-action")
        shell_preview_ready = self.backend.shell_preview_available()
        shell_button.set_sensitive(shell_preview_ready)

        def launch_shell(_button: Gtk.Button, watch: bool = False) -> None:
            profile = selected_id(shell_profile_row, shell_profile_ids, "tech")
            if not profile:
                self.window.toast("Není dostupný žádný profil pro Shell Preview.")
                return

            def worker() -> None:
                result = self.backend.launch_shell_preview(profile, watch=watch)
                GLib.idle_add(
                    self.window.toast,
                    (
                        (
                            "Live Shell Preview se spouští…"
                            if watch
                            else "Mutter Development Kit se spouští…"
                        )
                        if result.ok
                        else result.message
                    ),
                )

            threading.Thread(target=worker, daemon=True).start()

        shell_button.connect("clicked", launch_shell)
        shell_group.add(button_row("", shell_button))

        live_button = Gtk.Button(label="Spustit Live Preview")
        live_button.set_sensitive(shell_preview_ready)
        live_button.connect(
            "clicked",
            lambda button: launch_shell(button, watch=True),
        )
        shell_group.add(button_row("Auto restart", live_button))

        stop_live_button = Gtk.Button(label="Zastavit Live Preview")
        stop_live_button.set_sensitive(shell_preview_ready)

        def stop_live(_button: Gtk.Button) -> None:
            def worker() -> None:
                result = self.backend.stop_shell_preview()
                GLib.idle_add(
                    self.window.toast,
                    (
                        "Live Shell Preview zastaveno"
                        if result.ok
                        else result.message
                    ),
                )

            threading.Thread(target=worker, daemon=True).start()

        stop_live_button.connect("clicked", stop_live)
        shell_group.add(button_row("", stop_live_button))

        if not shell_preview_ready:
            shell_group.add(
                Adw.ActionRow(
                    title="Host helper není připravený",
                    subtitle="V kořeni projektu spusť ./dev-setup-fedora.sh",
                )
            )

        page.add(shell_group)

        tools = Adw.PreferencesGroup(title="Údržba")
        for title, label, args, destructive in [
            ("Stav Fedora Nova", "Zobrazit stav", ["status"], False),
            ("Diagnostika", "Spustit doctor", ["doctor"], False),
            ("Snapshot", "Vytvořit snapshot", ["snapshot", "create"], False),
            ("Nouzový režim", "Vypnout theme a dock", ["safe-mode"], True),
        ]:
            button = Gtk.Button(label=label)
            if destructive:
                button.add_css_class("destructive-action")
            button.connect(
                "clicked",
                lambda _button, command=args, name=title: (
                    self.window.run_output_dialog(name, command)
                ),
            )
            tools.add(button_row(title, button))
        page.add(tools)

        developer = Adw.PreferencesGroup(
            title="Ladění rozhraní",
            description=(
                "Ctrl+Shift+M otevře Adaptive Preview. "
                "Ctrl+Shift+I otevře GTK Inspector, pokud je povolený."
            ),
        )
        adaptive = Gtk.Button(label="Adaptive Preview")
        adaptive.connect(
            "clicked",
            lambda _button: self.window.toggle_adaptive_preview(),
        )
        developer.add(button_row("Responzivní náhled", adaptive))
        page.add(developer)
        return page
