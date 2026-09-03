#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

find "$ROOT" \
  \( -name .git -o -name _build -o -name .flatpak-builder \
     -o -name .flatpak-build-test -o -name .dev-build \) -prune \
  -o -name '*.sh' -type f -print0 |
  xargs -0 -r -n1 bash -n

mkdir -p "$ROOT/.dev-build/pycache"
PYTHONPYCACHEPREFIX="$ROOT/.dev-build/pycache" \
python3 -m compileall -q \
  "$ROOT/src/fedora_nova" \
  "$ROOT/core/scripts"

if command -v sassc >/dev/null 2>&1 || command -v sass >/dev/null 2>&1; then
  "$ROOT/core/scripts/build-theme-sass.sh" --check >/dev/null
else
  printf 'WARN: Sass compiler není dostupný; SCSS kontrola přeskočena.\n' >&2
fi

python3 - "$ROOT" <<'PY'
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

root = Path(sys.argv[1])
skip_dirs = {
    ".git", "_build", ".flatpak-builder", ".flatpak-build-test",
    ".dev-build", "generated",
}

def source_files(pattern):
    for path in root.rglob(pattern):
        if skip_dirs.isdisjoint(path.relative_to(root).parts):
            yield path

for path in source_files("*.json"):
    json.loads(path.read_text(encoding="utf-8"))

for path in list(source_files("*.xml")) + list(source_files("*.metainfo.xml")):
    ET.parse(path)

print("Python, Bash, Sass, JSON a XML kontroly prošly.")
PY
