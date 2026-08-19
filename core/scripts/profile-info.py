#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
REQUIRED = {
    "theme", "title", "description", "accent_name", "wallpaper",
    "dock_icon_size", "dock_opacity", "dock_color", "indicator",
    "accent", "secondary",
}

def load_profiles(builtin_json: Path, custom_dir: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(builtin_json.read_text(encoding="utf-8"))
    profiles: dict[str, dict[str, Any]] = {}
    for profile_id, profile in data.get("profiles", {}).items():
        item = dict(profile)
        item["kind"] = "builtin"
        item["id"] = profile_id
        profiles[profile_id] = item

    if custom_dir.is_dir():
        for file in sorted(custom_dir.glob("*.json")):
            try:
                item = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            profile_id = str(item.get("id", ""))
            if not PROFILE_RE.fullmatch(profile_id):
                continue
            if not REQUIRED.issubset(item):
                continue
            item = dict(item)
            item["kind"] = "custom"
            profiles[profile_id] = item
    return profiles

def shell_quote(value: Any) -> str:
    if isinstance(value, bool):
        value = "true" if value else "false"
    return shlex.quote(str(value))

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list")
    list_p.add_argument("builtin_json", type=Path)
    list_p.add_argument("custom_dir", type=Path)

    shell_p = sub.add_parser("shell")
    shell_p.add_argument("profile")
    shell_p.add_argument("builtin_json", type=Path)
    shell_p.add_argument("custom_dir", type=Path)

    json_p = sub.add_parser("json")
    json_p.add_argument("profile")
    json_p.add_argument("builtin_json", type=Path)
    json_p.add_argument("custom_dir", type=Path)

    args = parser.parse_args()
    profiles = load_profiles(args.builtin_json, args.custom_dir)

    if args.command == "list":
        for profile_id, item in profiles.items():
            print("\t".join([
                profile_id,
                str(item["title"]).replace("\t", " "),
                str(item["description"]).replace("\t", " "),
                str(item["kind"]),
            ]))
        return 0

    if not PROFILE_RE.fullmatch(args.profile):
        print("Neplatné ID profilu.", file=sys.stderr)
        return 2
    item = profiles.get(args.profile)
    if item is None:
        print(f"Profil neexistuje: {args.profile}", file=sys.stderr)
        return 3

    if args.command == "json":
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    mapping = {
        "PROFILE_ID": args.profile,
        "PROFILE_KIND": item["kind"],
        "THEME": item["theme"],
        "TITLE": item["title"],
        "DESCRIPTION": item["description"],
        "ACCENT_NAME": item["accent_name"],
        "WALL": item["wallpaper"],
        "ICON_SIZE": item["dock_icon_size"],
        "OPACITY": item["dock_opacity"],
        "DOCK_COLOR": item["dock_color"],
        "INDICATOR": item["indicator"],
        "DOT_COLOR": item["accent"],
        "DOT_BORDER": item["secondary"],
        "PRIMARY_COLOR": item["accent"],
        "SECONDARY_COLOR": item["secondary"],
    }
    for key, value in mapping.items():
        print(f"{key}={shell_quote(value)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
