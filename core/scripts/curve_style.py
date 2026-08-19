#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BEGIN = "/* NOVA_CURVE_START */"
END = "/* NOVA_CURVE_END */"


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "default" not in data or "presets" not in data:
        raise ValueError("Neplatný curves.json")
    return data


def render(preset_id: str, preset: dict[str, Any]) -> str:
    panel = int(preset["panel"])
    compact = int(preset["compact"])
    control = int(preset["control"])
    icon = int(preset["icon_plate"])
    card = int(preset["card"])
    popover = int(preset["popover"])
    dialog = int(preset["dialog"])
    dock = int(preset["dock"])
    handle = int(preset["slider_handle"])

    return f"""{BEGIN}
/* Fedora Nova 0.6 — Continuous Curve layer
 * preset: {preset_id}
 *
 * GNOME Shell does not expose Apple's private continuous-corner primitive.
 * This approximates it using large outer radii, proportionally smaller
 * nested radii, consistent icon plates and preserved true circles.
 */

#panel .panel-button,
#panel .panel-button.clock-display .clock {{
  border-radius: {panel}px;
}}

.quick-settings,
.datemenu-popover,
.popup-menu-content,
.candidate-popup-content,
.app-folder-dialog,
.switcher-list,
.workspace-switcher,
.screenshot-ui-panel,
#lookingGlassDialog {{
  border-radius: {popover}px;
}}

.modal-dialog,
.osd-window {{
  border-radius: {dialog}px;
}}

.notification-banner {{
  border-radius: {card}px;
}}

.quick-toggle-menu,
.datemenu-today-button,
.calendar,
.events-button,
.world-clocks-button,
.weather-button,
.message,
.media-message,
.search-section-content,
.workspace-thumbnail,
.window-caption {{
  border-radius: {card}px;
}}

.popup-menu-item,
.popup-sub-menu,
.quick-toggle,
.quick-toggle-has-menu,
.quick-toggle-menu .header .icon,
.calendar .calendar-month-header .calendar-month-label,
.calendar .calendar-month-header .pager-button,
.message-list-clear-button,
.message-media-control,
.modal-dialog-linked-button,
.search-entry,
.search-provider-icon,
.app-folder-dialog .folder-name-container,
.switcher-list .item-box,
.screenshot-ui-type-button,
.button {{
  border-radius: {control}px;
}}

.app-well-app .overview-icon,
.show-apps .overview-icon,
.app-folder .overview-icon,
.grid-search-result .overview-icon,
.search-provider-icon,
.dash-item-container .overview-icon {{
  border-radius: {icon}px;
}}

#dash .dash-background,
#dashtodockContainer #dash .dash-background,
.dash-to-dock .dash-background {{
  border-radius: {dock}px;
}}

.dash-label,
.tooltip,
.workspace-thumbnail .window-caption {{
  border-radius: {compact}px;
}}

.quick-toggle-has-menu .quick-toggle:ltr {{
  border-radius: {control}px 0 0 {control}px;
}}
.quick-toggle-has-menu .quick-toggle:rtl {{
  border-radius: 0 {control}px {control}px 0;
}}
.quick-toggle-has-menu .quick-toggle-menu-button:ltr {{
  border-radius: 0 {control}px {control}px 0;
}}
.quick-toggle-has-menu .quick-toggle-menu-button:rtl {{
  border-radius: {control}px 0 0 {control}px;
}}

.app-folder,
.app-folder-dialog .folder-name-container,
.workspace-thumbnail {{
  border-radius: {card}px;
}}

.calendar .calendar-day,
.quick-settings-system-item .icon-button,
.quick-settings-system-item .power-item,
.screenshot-ui-capture-button,
.toggle-switch,
.avatar,
.user-icon,
#panel #panelActivities .workspace-dot,
.app-grid-running-dot,
.app-well-app-running-dot {{
  border-radius: 999px;
}}

.slider {{
  -slider-handle-radius: {handle}px;
}}
{END}"""


def strip_existing(text: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    return pattern.sub("", text).rstrip()


def update_file(file: Path, block: str) -> bool:
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return False
    updated = strip_existing(text) + "\n\n" + block + "\n"
    if updated == text:
        return False
    file.write_text(updated, encoding="utf-8")
    return True


def find_theme_files(roots: list[Path]) -> list[Path]:
    files: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for file in root.glob("Fedora-Nova*/gnome-shell/gnome-shell.css"):
            files[str(file.resolve())] = file
    return sorted(files.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Fedora Nova curvature engine")
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list")
    list_p.add_argument("config", type=Path)

    render_p = sub.add_parser("render")
    render_p.add_argument("preset")
    render_p.add_argument("config", type=Path)

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("preset")
    apply_p.add_argument("config", type=Path)
    apply_p.add_argument("roots", nargs="+", type=Path)

    args = parser.parse_args()
    data = load_config(args.config)
    presets = data["presets"]

    if args.command == "list":
        for preset_id, preset in presets.items():
            print("\t".join([preset_id, str(preset["title"]), str(preset["description"])]))
        return 0

    if args.preset not in presets:
        print(f"Neznámý curvature preset: {args.preset}", file=sys.stderr)
        return 2

    block = render(args.preset, presets[args.preset])
    if args.command == "render":
        print(block)
        return 0

    files = find_theme_files(args.roots)
    changed = 0
    for file in files:
        changed += int(update_file(file, block))
    print(f"{changed}\t{len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
