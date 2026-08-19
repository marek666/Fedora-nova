#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BEGIN = '/* NOVA_HOVER_START */'
END = '/* NOVA_HOVER_END */'
PSEUDOS = (':hover', ':focus', ':selected', ':active', ':checked', ':outlined')
ICON_BIN = '.overview-icon > StBoxLayout > StBin'


def join_selectors(selectors: list[str]) -> str:
    return ',\n'.join(dict.fromkeys(selectors))


def stateful(base: str, *, include_base: bool = True) -> list[str]:
    selectors: list[str] = []
    if include_base:
        selectors.append(base)
    selectors.extend(f'{base}{pseudo}' for pseudo in PSEUDOS)
    selectors.append(f'{base}.focused')
    return selectors


def dock_roots() -> list[str]:
    return [
        '.dash-item-container',
        '#dash .dash-item-container',
        '#dashtodockContainer .dash-item-container',
        '#dashtodockContainer #dash .dash-item-container',
        '#dashtodockContainer.dashtodock #dash .dash-item-container',
    ]


def dock_children(*, include_show_apps: bool = True) -> list[str]:
    children = ['.overview-tile', '.app-well-app']
    if include_show_apps:
        children.append('.show-apps')
    return children


def dock_overview_icon_selector() -> str:
    selectors: list[str] = []
    for root in dock_roots():
        selectors.extend(f'{root_state} .overview-icon' for root_state in stateful(root))
        selectors.extend(stateful(f'{root} .overview-icon'))
        for child in dock_children():
            selectors.extend(
                f'{child_state} .overview-icon'
                for child_state in stateful(f'{root} {child}')
            )
    return join_selectors(selectors)


def grid_overview_icon_selector() -> str:
    selectors = ['.overview-tile .overview-icon']
    selectors.extend(
        f'{tile_state} .overview-icon'
        for tile_state in stateful('.overview-tile', include_base=False)
    )
    selectors.extend(stateful('.overview-tile .overview-icon', include_base=False))
    return join_selectors(selectors)


def show_apps_active_selector() -> str:
    selectors: list[str] = []
    for root in dock_roots():
        selectors.extend(
            f'{root} {show_apps_state} .overview-icon'
            for show_apps_state in stateful('.show-apps', include_base=False)
        )
        selectors.extend(
            f'{root_state} .show-apps .overview-icon'
            for root_state in stateful(root, include_base=False)
        )
        selectors.extend(
            stateful(f'{root} .show-apps .overview-icon', include_base=False)
        )
    return join_selectors(selectors)


def tile_active_selector() -> str:
    selectors: list[str] = []
    selectors.extend(
        f'{tile_state} .overview-icon'
        for tile_state in stateful('.overview-tile', include_base=False)
    )
    selectors.extend(stateful('.overview-tile .overview-icon', include_base=False))

    for root in dock_roots():
        selectors.extend(
            f'{root_state} .overview-icon'
            for root_state in stateful(root, include_base=False)
        )
        selectors.extend(stateful(f'{root} .overview-icon', include_base=False))
        for child in dock_children():
            selectors.extend(
                f'{child_state} .overview-icon'
                for child_state in stateful(f'{root} {child}', include_base=False)
            )

    return join_selectors(selectors)


def overview_icon_bin_states(base: str) -> list[str]:
    selectors = [
        f'{base} .overview-icon{pseudo} > StBoxLayout > StBin'
        for pseudo in PSEUDOS
    ]
    selectors.append(f'{base} .overview-icon.focused > StBoxLayout > StBin')
    return selectors


def rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip('#')
    if len(value) != 6:
        raise ValueError(f'Neplatná barva: {hex_color}')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def load_theme_colors(
    profiles_json: Path,
    custom_dir: Path,
) -> dict[str, dict[str, str]]:
    data = json.loads(profiles_json.read_text(encoding='utf-8'))
    result: dict[str, dict[str, str]] = {}

    def add(item: dict[str, Any]) -> None:
        result[str(item['theme'])] = {
            'accent': str(item['accent']),
            'secondary': str(item['secondary']),
            'dock': str(item.get('dock_color', item.get('panel', '#08091B'))),
            'border': str(item.get('border', item['secondary'])),
        }

    for item in data.get('profiles', {}).values():
        add(item)

    if custom_dir.is_dir():
        for file in custom_dir.glob('*.json'):
            try:
                add(json.loads(file.read_text(encoding='utf-8')))
            except (OSError, KeyError, json.JSONDecodeError):
                continue

    return result


def dock_reset(dock: str, border: str) -> str:
    dr, dg, db = rgb(dock)
    br, bg, bb = rgb(border)
    dock_icon_reset = dock_overview_icon_selector()
    return f'''
/* Dash to Dock v105 paints $remark_color directly on .overview-icon.
 * Override that exact layer and keep Fedora Nova in control of the dock. */
#dashtodockContainer #dash .dash-background,
#dashtodockContainer.dashtodock #dash .dash-background,
#dashtodockContainer.bottom #dash .dash-background,
#dashtodockContainer.top #dash .dash-background,
#dashtodockContainer.left #dash .dash-background,
#dashtodockContainer.right #dash .dash-background {{
  background-color: rgba({dr}, {dg}, {db}, 0.94) !important;
  border-color: rgba({br}, {bg}, {bb}, 0.82) !important;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.34) !important;
}}
'''.strip()


def common_reset(dock: str, border: str) -> str:
    grid_icon_reset = grid_overview_icon_selector()
    return f'''
.app-well-app .overview-icon,
.show-apps .overview-icon,
.grid-search-result .overview-icon,
.dash-item-container .overview-icon {{
  background-color: transparent !important;
  box-shadow: none !important;
  border-radius: 999px !important;
}}

.app-folder .overview-icon {{
  background-color: transparent !important;
  background-image: none !important;
}}

.app-well-app:hover .overview-icon,
.app-well-app:focus .overview-icon,
.show-apps:hover .overview-icon,
.grid-search-result:hover .overview-icon,
.dash-item-container:hover .overview-icon {{
  background-color: rgba(46, 216, 232, 0.20) !important;
  background-image: none !important;
  border: 0 !important;
  border-radius: 999px !important;
  box-shadow: 0 0 0 55px rgba(46, 216, 232, 0.68), inset 0 0 0 50px rgba(96, 64, 110, 0.78) !important;
}}

.app-folder:hover .overview-icon {{
  background-color: transparent !important;
  background-image: url("assets/app-folder-squircle.svg") !important;
  box-shadow: none !important;
}}

.overview-tile,
.overview-tile:hover,
.overview-tile:focus,
.overview-tile:selected,
.overview-tile:active,
.overview-tile:checked,
.overview-tile:outlined,
.overview-tile.app-folder,
.overview-tile.app-folder:hover,
.overview-tile.app-folder:focus,
.overview-tile.app-folder:selected,
.overview-tile.app-folder:active,
.overview-tile.app-folder:checked,
.overview-tile.app-folder:outlined {{
  background-color: transparent !important;
  background-image: none !important;
  border-color: transparent !important;
  box-sizing: border-box !important;
  box-shadow: none !important;
}}

#dashtodockContainer #dash .overview-tile:hover,
#dashtodockContainer #dash .overview-tile:focus,
#dashtodockContainer #dash .overview-tile:selected,
#dashtodockContainer #dash .overview-tile:active,
#dashtodockContainer #dash .overview-tile:checked,
#dashtodockContainer #dash .overview-tile:outlined,
#dashtodockContainer #dash .overview-tile.app-folder,
#dashtodockContainer #dash .overview-tile.app-folder:hover,
#dashtodockContainer #dash .overview-tile.app-folder:focus,
#dashtodockContainer #dash .overview-tile.app-folder:selected,
#dashtodockContainer #dash .overview-tile.app-folder:active,
#dashtodockContainer #dash .overview-tile.app-folder:checked,
#dashtodockContainer #dash .overview-tile.app-folder:outlined {{
  background-color: transparent !important;
  background-image: none !important;
  border-color: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}}

{dock_reset(dock, border)}
'''.strip()


def icon_bin_selector(states: bool = False, dock_only: bool = False) -> str:
    grid_bases = ['.overview-tile']
    bases = dock_roots() if dock_only else grid_bases

    if not states:
        selectors: list[str] = []
        for base in bases:
            selectors.append(f'{base} {ICON_BIN}')
            if dock_only:
                selectors.extend(
                    f'{base} {child} {ICON_BIN}'
                    for child in dock_children(include_show_apps=False)
                )
        return join_selectors(selectors)

    selectors: list[str] = []
    for base in bases:
        selectors.extend(
            f'{base_state} {ICON_BIN}'
            for base_state in stateful(base, include_base=False)
        )
        selectors.extend(overview_icon_bin_states(base))
        if dock_only:
            for child in dock_children(include_show_apps=False):
                selectors.extend(
                    f'{child_state} {ICON_BIN}'
                    for child_state in stateful(
                        f'{base} {child}',
                        include_base=False,
                    )
                )
    return join_selectors(selectors)


def circle_body(
    accent: str,
    secondary: str,
    dock: str,
    border: str,
    *,
    grid_halo: int,
    dock_halo: int,
) -> str:
    ar, ag, ab = rgb(accent)
    sr, sg, sb = rgb(secondary)
    reset = common_reset(dock, border)

    grid_normal = icon_bin_selector(False)
    grid_active = icon_bin_selector(True)
    dock_normal = icon_bin_selector(False, dock_only=True)
    dock_active = icon_bin_selector(True, dock_only=True)

    return reset + f'''

{grid_normal},
{dock_normal} {{
  background-color: rgba(0, 0, 0, 0.01) !important;
  background-image: none !important;
  border: 0 !important;
  border-radius: 999px !important;
  box-shadow: none !important;
  transition-duration: 100ms;
}}
    
/* App grid: large external halo, especially visible around visually small
 * icons such as Files. No padding or margin changes. */
{grid_active} {{
  background-color: rgba({ar}, {ag}, {ab}, 0.18) !important;
  background-image: none !important;
  border: 0 !important;
  border-radius: 999px !important;
  box-shadow:
    0 0 0 {grid_halo}px rgba({ar}, {ag}, {ab}, 0.15),
    inset 0 0 0 2px rgba({ar}, {ag}, {ab}, 0.62),
    inset 0 0 0 3px rgba({sr}, {sg}, {sb}, 0.12) !important;
}}

/* Dock has less free space, so use a smaller but still colored halo. */
{dock_active} {{
  background-color: rgba({ar}, {ag}, {ab}, 0.20) !important;
  background-image: none !important;
  border: 0 !important;
  border-radius: 999px !important;
  box-shadow:
    0 0 0 {dock_halo}px rgba({ar}, {ag}, {ab}, 0.17),
    inset 0 0 0 2px rgba({ar}, {ag}, {ab}, 0.68),
    inset 0 0 0 3px rgba({sr}, {sg}, {sb}, 0.14) !important;
}}

/* Never paint the icon texture or folder miniature itself. */
.overview-tile .overview-icon > StBoxLayout > StBin > StIcon,
.overview-tile .overview-icon > StBoxLayout > StBin > StWidget {{
  background-color: transparent !important;
  background-image: none !important;
  border: 0 !important;
  box-shadow: none !important;
}}

.app-folder:hover .overview-icon > StBoxLayout > StBin,
.app-folder:hover .overview-icon > StBoxLayout > StBin {{
  background-color: transparent !important;
  background-image: none !important;
  border: 0 !important;
  box-shadow: none !important;
}}
'''


def render(
    mode: str,
    accent: str,
    secondary: str,
    dock: str,
    border: str,
) -> str:
    ar, ag, ab = rgb(accent)
    sr, sg, sb = rgb(secondary)
    reset = common_reset(dock, border)

    if mode == 'none':
        body = reset
    elif mode == 'tile':
        body = reset + f'''

{tile_active_selector()} {{
  background-color: rgba({ar}, {ag}, {ab}, 0.16) !important;
  border: 1px solid rgba({ar}, {ag}, {ab}, 0.48) !important;
  box-shadow: inset 0 0 0 50px rgba({sr}, {sg}, {sb}, 0.12) !important;
}}
'''
    elif mode == 'circle-compact':
        body = circle_body(
            accent, secondary, dock, border,
            grid_halo=5, dock_halo=3,
        )
    elif mode == 'circle':
        body = circle_body(
            accent, secondary, dock, border,
            grid_halo=10, dock_halo=5,
        )
    else:
        raise ValueError(f'Neznámý hover režim: {mode}')

    return (
        f'{BEGIN}\n'
        f'/* Fedora Nova hover mode: {mode}; stable icon-bin halo */\n'
        f'{body.strip()}\n'
        f'{END}'
    )


def strip_block(text: str) -> str:
    return re.sub(
        re.escape(BEGIN) + r'.*?' + re.escape(END),
        '',
        text,
        flags=re.S,
    ).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'mode',
        choices=['circle', 'circle-compact', 'tile', 'none'],
    )
    parser.add_argument('profiles_json', type=Path)
    parser.add_argument('custom_dir', type=Path)
    parser.add_argument('roots', nargs='+', type=Path)
    args = parser.parse_args()

    colors = load_theme_colors(args.profiles_json, args.custom_dir)
    changed = 0
    total = 0
    seen: set[Path] = set()

    for root in args.roots:
        if not root.is_dir():
            continue
        for css in root.glob('Fedora-Nova*/gnome-shell/gnome-shell.css'):
            resolved = css.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            total += 1
            palette = colors.get(css.parent.parent.name)
            if not palette:
                continue
            text = css.read_text(encoding='utf-8')
            updated = strip_block(text) + '\n\n' + render(
                args.mode,
                palette['accent'],
                palette['secondary'],
                palette['dock'],
                palette['border'],
            ) + '\n'
            if updated != text:
                css.write_text(updated, encoding='utf-8')
                changed += 1

    print(f'{changed}\t{total}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
