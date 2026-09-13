#!/usr/bin/env python3
"""Prepare a preview-only Dash to Dock 105 copy with stage-safe sizing."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile


def patch_sources(directory):
    edits = []
    for dimension, argument in (("height", "forWidth"), ("width", "forHeight")):
        head = f"    vfunc_get_preferred_{dimension}({argument}) {{\n"
        body = f"        const [min{dimension.title()}, nat{dimension.title()}] = super.vfunc_get_preferred_{dimension}.call(this, {argument});"
        edits.append(("dash.js", head + body,
                      head + "        if (!this.get_stage())\n            return [0, 0];\n" + body))
    old = "if (this.mainDock.isHorizontal && !this.settings.dockFixed)"
    new = "if (this.mainDock.get_stage() &&\n                    this.mainDock.isHorizontal &&\n                    !this.settings.dockFixed)"
    tail = "\n                    return this.mainDock.get_preferred_height(...args);"
    edits.append(("docking.js", old + tail, new + tail))
    for name, before, after in edits:
        path = directory / name
        content = path.read_text()
        if content.count(after) == 1 and before not in content:
            continue
        if content.count(before) != 1 or after in content:
            raise ValueError(f"Unexpected Dash to Dock 105 source in {name}; preview copy was not installed")
        path.write_text(content.replace(before, after, 1))


def prepare(source, target):
    metadata = json.loads((source / "metadata.json").read_text())
    if metadata.get("uuid") != "dash-to-dock@micxgx.gmail.com":
        raise ValueError("Unexpected extension UUID")
    if metadata.get("version") != 105:
        print("Preview: Dash to Dock stage patch supports version 105 only; using the installed extension unchanged.")
        return False
    if target.exists() or target.is_symlink():
        raise ValueError("Preview extension destination must be absent")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dock-stage-", dir=target.parent) as temporary:
        staged = Path(temporary) / "extension"
        shutil.copytree(source, staged)
        patch_sources(staged)
        os.replace(staged, target)
    print("Preview: Dash to Dock 105 copied with stage-safe sizing.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        prepare(args.source, args.target)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Preview dock preparation failed: {exc}\n")
