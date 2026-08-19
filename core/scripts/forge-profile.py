#!/usr/bin/env python3
from __future__ import annotations

import argparse
import colorsys
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path

HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")

GNOME_ACCENTS = {
    "blue": "#3584e4",
    "teal": "#2190a4",
    "green": "#3a944a",
    "yellow": "#c88800",
    "orange": "#ed5b00",
    "red": "#e62d42",
    "pink": "#d56199",
    "purple": "#9141ac",
    "slate": "#6f8396",
}

TECH_TOKENS = {
    "#07111f": "bg",
    "#040a14": "panel",
    "#091424": "large",
    "#122640": "surface",
    "#172e4b": "surface2",
    "#1c2739": "card",
    "#2ed8e8": "accent",
    "#6fe7f7": "accent_bright",
    "#06131a": "accent_fg",
    "#8c5cff": "secondary",
    "#eaf2ff": "text",
    "#92a6bf": "muted",
    "#31516d": "border",
}

def normalize_hex(value: str) -> str:
    if not HEX_RE.fullmatch(value):
        raise ValueError(f"Neplatná HEX barva: {value}")
    return "#" + value.lstrip("#").upper()

def rgb(value: str) -> tuple[int, int, int]:
    value = normalize_hex(value).lstrip("#")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

def hex_color(value) -> str:
    vals = [max(0, min(255, round(v))) for v in value]
    return "#" + "".join(f"{v:02X}" for v in vals)

def mix(a: str, b: str, weight_b: float) -> str:
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    w = max(0.0, min(1.0, weight_b))
    return hex_color((ar*(1-w)+br*w, ag*(1-w)+bg*w, ab*(1-w)+bb*w))

def rotate_hue(color: str, degrees: float) -> str:
    r, g, b = [v / 255 for v in rgb(color)]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + degrees / 360.0) % 1.0
    rr, gg, bb = colorsys.hls_to_rgb(h, max(0.48, min(0.62, l)), max(0.72, s))
    return hex_color((rr*255, gg*255, bb*255))

def srgb_to_linear(channel: float) -> float:
    channel /= 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

def luminance(color: str) -> float:
    r, g, b = rgb(color)
    return 0.2126*srgb_to_linear(r) + 0.7152*srgb_to_linear(g) + 0.0722*srgb_to_linear(b)

def accent_foreground(color: str) -> str:
    return "#071018" if luminance(color) > 0.29 else "#F8FBFF"

def nearest_gnome_accent(color: str) -> str:
    cr, cg, cb = rgb(color)
    def distance(candidate: str) -> float:
        rr, gg, bb = rgb(candidate)
        return math.sqrt((cr-rr)**2 + (cg-gg)**2 + (cb-bb)**2)
    return min(GNOME_ACCENTS, key=lambda name: distance(GNOME_ACCENTS[name]))

def slugify(name: str) -> str:
    slug = SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        raise ValueError("Název nevytvořil platné ID.")
    return slug[:48]

def title_from_name(name: str) -> str:
    return " ".join(part for part in re.split(r"\s+", name.strip()) if part)[:80]

def palette(primary: str, secondary: str) -> dict[str, str]:
    return {
        "bg": mix("#06101D", primary, 0.045),
        "panel": mix("#030812", primary, 0.035),
        "large": mix("#091424", primary, 0.085),
        "surface": mix("#122640", primary, 0.12),
        "surface2": mix("#172E4B", primary, 0.17),
        "card": mix("#1C2739", primary, 0.11),
        "accent": primary,
        "accent_bright": mix(primary, "#FFFFFF", 0.28),
        "accent_fg": accent_foreground(primary),
        "secondary": secondary,
        "text": mix("#F8FBFF", primary, 0.025),
        "muted": mix("#98A8BD", primary, 0.08),
        "border": mix("#31516D", primary, 0.27),
        "shadow": "#000000",
    }

def replace_css(template: str, colors: dict[str, str], title: str) -> str:
    css = template
    css = re.sub(r"Fedora Nova 0\.\d+\.\d+", "Fedora Nova 0.6.0", css)
    css = re.sub(r"Profile: Nova Tech", f"Profile: Nova Forge — {title}", css)

    rgba_roles = {
        (46, 216, 232): "accent",
        (111, 231, 247): "accent_bright",
        (6, 19, 26): "accent_fg",
        (140, 92, 255): "secondary",
        (234, 242, 255): "text",
        (146, 166, 191): "muted",
        (49, 81, 109): "border",
    }
    for old_rgb, role in rgba_roles.items():
        nr, ng, nb = rgb(colors[role])
        pattern = re.compile(
            rf"rgba\(\s*{old_rgb[0]}\s*,\s*{old_rgb[1]}\s*,\s*{old_rgb[2]}\s*,",
            re.IGNORECASE,
        )
        css = pattern.sub(f"rgba({nr}, {ng}, {nb},", css)

    for old_hex, role in TECH_TOKENS.items():
        css = re.sub(re.escape(old_hex), colors[role], css, flags=re.IGNORECASE)

    if re.search(r"(blur-effect|filter\s*:\s*blur)", css, re.IGNORECASE):
        raise ValueError("Generovaný theme neprošel výkonovou kontrolou blur.")
    if css.count("{") != css.count("}"):
        raise ValueError("Generovaný theme má nevyvážené CSS závorky.")
    return css

def wallpaper_svg(primary: str, secondary: str, colors: dict[str, str], title: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="2560" height="1600" viewBox="0 0 2560 1600">
  <defs>
    <radialGradient id="bg" cx="72%" cy="26%" r="92%">
      <stop offset="0" stop-color="{colors["surface2"]}"/>
      <stop offset=".42" stop-color="{colors["large"]}"/>
      <stop offset="1" stop-color="{colors["panel"]}"/>
    </radialGradient>
    <linearGradient id="primary" x1="0" x2="1">
      <stop offset="0" stop-color="{primary}" stop-opacity=".10"/>
      <stop offset=".48" stop-color="{primary}" stop-opacity=".95"/>
      <stop offset="1" stop-color="{colors["accent_bright"]}" stop-opacity=".25"/>
    </linearGradient>
    <linearGradient id="secondary" x1="0" x2="1">
      <stop offset="0" stop-color="{secondary}" stop-opacity=".08"/>
      <stop offset=".55" stop-color="{secondary}" stop-opacity=".78"/>
      <stop offset="1" stop-color="{secondary}" stop-opacity=".08"/>
    </linearGradient>
    <pattern id="grid" width="92" height="92" patternUnits="userSpaceOnUse">
      <path d="M92 0H0V92" fill="none" stroke="{colors["border"]}" stroke-opacity=".075"/>
    </pattern>
  </defs>
  <rect width="2560" height="1600" fill="url(#bg)"/>
  <rect width="2560" height="1600" fill="url(#grid)"/>
  <g fill="none">
    <path d="M-140 1070 C360 740 690 1320 1160 970 S1880 500 2700 820"
          stroke="url(#primary)" stroke-width="9"/>
    <path d="M-120 1200 C380 900 760 1370 1280 1030 S2050 670 2700 980"
          stroke="url(#secondary)" stroke-width="5"/>
    <path d="M-100 525 C430 250 870 670 1360 420 S2190 230 2700 500"
          stroke="{colors["accent_bright"]}" stroke-opacity=".27" stroke-width="3"/>
  </g>
  <g fill="none" stroke="{primary}" stroke-opacity=".105">
    <circle cx="1840" cy="620" r="112"/><circle cx="1840" cy="620" r="212"/>
    <circle cx="1840" cy="620" r="322"/><circle cx="1840" cy="620" r="442"/>
  </g>
  <g fill="{colors["text"]}" fill-opacity=".28">
    <circle cx="420" cy="310" r="2"/><circle cx="740" cy="1320" r="2"/>
    <circle cx="1450" cy="250" r="2"/><circle cx="2180" cy="1210" r="2"/>
  </g>
  <metadata>Fedora Nova Forge profile: {title}</metadata>
</svg>'''

def ptyxis_palette(title: str, colors: dict[str, str]) -> str:
    return f'''[Palette]
Name=Fedora Nova Custom {title}
Background={colors["bg"]}
Foreground={colors["text"]}
Cursor={colors["accent"]}
CursorForeground={colors["accent_fg"]}
SelectionBackground={colors["secondary"]}
SelectionForeground={colors["text"]}
Color0=#10182B
Color1=#FF5C7A
Color2=#35D07F
Color3=#F4B942
Color4=#4AA8FF
Color5={colors["secondary"]}
Color6={colors["accent"]}
Color7=#D7E3F5
Color8=#526078
Color9=#FF7890
Color10=#59E49A
Color11=#FFD16A
Color12=#75BDFF
Color13={colors["accent_bright"]}
Color14={colors["secondary"]}
Color15=#FFFFFF
'''

def paths() -> dict[str, Path]:
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    app = Path(__file__).resolve().parent.parent
    return {
        "app": app,
        "themes": data / "themes",
        "wallpapers": data / "backgrounds/fedora-nova",
        "palettes": data / "org.gnome.Ptyxis/palettes",
        "custom": config / "fedora-nova/custom-profiles",
        "state": config / "fedora-nova/current-profile",
    }

def create(args: argparse.Namespace) -> int:
    title = title_from_name(args.name)
    slug = slugify(title)
    profile_id = f"custom-{slug}"
    primary = normalize_hex(args.primary)
    secondary = normalize_hex(args.secondary) if args.secondary else rotate_hue(primary, 145)
    colors = palette(primary, secondary)
    loc = paths()

    theme_name = f"Fedora-Nova-Custom-{slug}"
    wallpaper_name = f"custom-{slug}.svg"
    palette_name = f"Fedora Nova Custom {title}.palette"

    template = (loc["app"] / "themes/Fedora-Nova-Tech/gnome-shell/gnome-shell.css").read_text(
        encoding="utf-8"
    )
    css = replace_css(template, colors, title)

    theme_dir = loc["themes"] / theme_name / "gnome-shell"
    for directory in (theme_dir, loc["wallpapers"], loc["palettes"], loc["custom"]):
        directory.mkdir(parents=True, exist_ok=True)

    (theme_dir / "gnome-shell.css").write_text(css, encoding="utf-8")
    (loc["wallpapers"] / wallpaper_name).write_text(
        wallpaper_svg(primary, secondary, colors, title), encoding="utf-8"
    )
    (loc["palettes"] / palette_name).write_text(
        ptyxis_palette(title, colors), encoding="utf-8"
    )

    metadata = {
        "id": profile_id,
        "kind": "custom",
        "theme": theme_name,
        "title": f"Nova {title}",
        "description": f"Vlastní Forge profil: {primary} + {secondary}.",
        "accent_name": nearest_gnome_accent(primary),
        "wallpaper": wallpaper_name,
        "palette": palette_name,
        "dock_icon_size": args.icon_size,
        "dock_opacity": args.opacity,
        "dock_color": colors["panel"],
        "indicator": args.indicator,
        **colors,
    }
    (loc["custom"] / f"{profile_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(profile_id)
    return 0

def delete(args: argparse.Namespace) -> int:
    profile_id = args.profile
    if not profile_id.startswith("custom-"):
        raise ValueError("Mazat lze pouze profily začínající custom-.")
    loc = paths()
    metadata_file = loc["custom"] / f"{profile_id}.json"
    if not metadata_file.is_file():
        raise ValueError(f"Vlastní profil neexistuje: {profile_id}")
    current = loc["state"].read_text(encoding="utf-8").strip() if loc["state"].is_file() else ""
    if current == profile_id:
        raise ValueError("Aktivní vlastní profil nelze smazat. Nejprve přepni jiný profil.")

    item = json.loads(metadata_file.read_text(encoding="utf-8"))
    shutil.rmtree(loc["themes"] / item["theme"], ignore_errors=True)
    try:
        (loc["wallpapers"] / item["wallpaper"]).unlink()
    except FileNotFoundError:
        pass
    palette_name = item.get("palette")
    if palette_name:
        try:
            (loc["palettes"] / palette_name).unlink()
        except FileNotFoundError:
            pass
    metadata_file.unlink()
    print(profile_id)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Fedora Nova Forge")
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create")
    create_p.add_argument("name")
    create_p.add_argument("primary")
    create_p.add_argument("secondary", nargs="?")
    create_p.add_argument("--icon-size", type=int, default=42, choices=range(24, 65))
    create_p.add_argument("--opacity", type=float, default=0.78)
    create_p.add_argument(
        "--indicator", default="SEGMENTED",
        choices=["DEFAULT", "DOTS", "SQUARES", "DASHES", "SEGMENTED", "SOLID", "DOT"],
    )

    delete_p = sub.add_parser("delete")
    delete_p.add_argument("profile")

    args = parser.parse_args()
    try:
        if args.command == "create":
            if not 0.25 <= args.opacity <= 1.0:
                raise ValueError("Opacity musí být mezi 0.25 a 1.0.")
            return create(args)
        return delete(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
