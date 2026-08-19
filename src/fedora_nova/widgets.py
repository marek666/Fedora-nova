from __future__ import annotations

from pathlib import Path
from typing import Any

from gi.repository import Adw, Gdk, Gtk


def button_row(title: str, button: Gtk.Button, subtitle: str = "") -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    button.set_valign(Gtk.Align.CENTER)
    row.add_suffix(button)
    row.set_activatable_widget(button)
    return row


def combo_row(
    title: str,
    items: list[tuple[str, str]],
    current: str,
    subtitle: str = "",
    fallback: str | None = None,
) -> tuple[Adw.ComboRow, list[str]]:
    ids = [item[0] for item in items]
    labels = [item[1] for item in items]
    row = Adw.ComboRow(title=title, subtitle=subtitle)
    row.set_model(Gtk.StringList.new(labels))
    if current in ids:
        selected = ids.index(current)
    elif fallback in ids:
        selected = ids.index(fallback)
    else:
        selected = 0
    if ids:
        row.set_selected(selected)
    return row, ids


def selected_id(row: Adw.ComboRow, ids: list[str], fallback: str = "") -> str:
    if not ids:
        return fallback
    index = row.get_selected()
    if 0 <= index < len(ids):
        return ids[index]
    if fallback in ids:
        return fallback
    return ids[0]


def desktop_preview(profile: dict[str, Any], wallpaper: Path) -> Gtk.Widget:
    title = str(profile.get("title", "Nova Tech"))

    frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    frame.add_css_class("nova-preview-frame")
    frame.set_size_request(-1, 270)
    frame.set_hexpand(True)

    overlay = Gtk.Overlay()
    overlay.set_hexpand(True)
    overlay.set_vexpand(True)
    overlay.set_size_request(-1, 270)
    frame.append(overlay)

    if wallpaper.is_file():
        picture = Gtk.Picture.new_for_filename(str(wallpaper))
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        overlay.set_child(picture)
    else:
        fallback = Gtk.Box()
        fallback.add_css_class("nova-preview-wallpaper-fallback")
        fallback.set_hexpand(True)
        fallback.set_vexpand(True)
        overlay.set_child(fallback)

    shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    shell.add_css_class("nova-preview-shell")
    shell.set_halign(Gtk.Align.FILL)
    shell.set_valign(Gtk.Align.FILL)
    shell.set_hexpand(True)
    shell.set_vexpand(True)
    overlay.add_overlay(shell)

    topbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    topbar.add_css_class("nova-preview-topbar")
    topbar.set_hexpand(True)
    shell.append(topbar)

    brand = Gtk.Label(label=title, xalign=0)
    brand.add_css_class("nova-preview-brand")
    brand.set_hexpand(True)
    topbar.append(brand)

    clock = Gtk.Label(label="úterý 8:14")
    clock.add_css_class("nova-preview-clock")
    topbar.append(clock)

    status = Gtk.Label(label="cs  100 %", xalign=1)
    status.add_css_class("nova-preview-status")
    status.set_hexpand(True)
    topbar.append(status)

    workspace = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    workspace.add_css_class("nova-preview-workspace")
    workspace.set_vexpand(True)
    shell.append(workspace)

    side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    side.add_css_class("nova-preview-side")
    workspace.append(side)

    for index in range(4):
        dot = Gtk.Box()
        dot.add_css_class("nova-preview-dot")
        if index == 0:
            dot.add_css_class("active")
        side.append(dot)

    window = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    window.add_css_class("nova-preview-window")
    window.set_hexpand(True)
    window.set_vexpand(True)
    workspace.append(window)

    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    header.add_css_class("nova-preview-window-header")
    window.append(header)
    for _index in range(3):
        control = Gtk.Box()
        control.add_css_class("nova-preview-control")
        header.append(control)

    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    content.set_vexpand(True)
    window.append(content)

    for index in range(3):
        card = Gtk.Box()
        card.add_css_class("nova-preview-card")
        if index == 1:
            card.add_css_class("secondary")
        card.set_hexpand(True)
        card.set_vexpand(True)
        content.append(card)

    dock = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    dock.add_css_class("nova-preview-dock")
    dock.set_halign(Gtk.Align.CENTER)
    shell.append(dock)

    for index in range(7):
        icon = Gtk.Box()
        icon.add_css_class("nova-preview-dock-icon")
        if index in {1, 4}:
            icon.add_css_class("secondary")
        dock.append(icon)

    return frame


def color_row(title: str, value: str) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle=value)
    swatch = Gtk.DrawingArea()
    swatch.set_content_width(30)
    swatch.set_content_height(30)
    swatch.set_valign(Gtk.Align.CENTER)
    swatch.add_css_class("color-swatch")

    rgba = Gdk.RGBA()
    if not rgba.parse(value):
        rgba.parse("#777777")

    def draw(_area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(width / 2, height / 2, min(width, height) / 2 - 2, 0, 6.283)
        cr.fill()

    swatch.set_draw_func(draw)
    row.add_suffix(swatch)
    return row
