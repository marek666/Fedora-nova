#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$ROOT/core/themes-src/scss"
GENERATED_DIR="$ROOT/.dev-build/theme-sass"
PROFILES_JSON="$ROOT/core/config/profiles.json"

usage() {
  cat <<'EOF'
Pouziti: build-theme-sass.sh [--check|--generate|--apply]

  --check     zkompiluje Sass do docasneho adresare a zkontroluje markery
  --generate  zkompiluje Sass vrstvy do .dev-build/theme-sass
  --apply     zkompiluje Sass a nahradi NOVA_CURVE/NOVA_HOVER bloky v themes/

Fedora Nova nepouziva Tailwind pro GNOME Shell. Sass generuje ciste CSS, ktere
se da vydat bez runtime build zavislosti.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

mode="${1:---generate}"
case "$mode" in
  --help|-h) usage; exit 0 ;;
  --check|--generate|--apply) ;;
  *) usage >&2; exit 2 ;;
esac

if command -v sassc >/dev/null 2>&1; then
  compiler=sassc
elif command -v sass >/dev/null 2>&1; then
  compiler=sass
else
  die "Chybi Sass compiler. Na Fedore nainstaluj napr. balicek sassc."
fi

if [[ "$mode" == "--check" ]]; then
  OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fedora-nova-sass.XXXXXX")"
  trap 'rm -rf "$OUT_DIR"' EXIT
else
  OUT_DIR="$GENERATED_DIR"
  mkdir -p "$OUT_DIR"
fi

compile_scss() {
  local source_file="$1"
  local output_file="$2"
  mkdir -p "$(dirname -- "$output_file")"

  if [[ "$compiler" == sassc ]]; then
    sassc -t expanded "$source_file" "$output_file"
  else
    sass --style=expanded "$source_file" "$output_file"
  fi
}

theme_for_profile() {
  local profile="$1"
  python3 - "$PROFILES_JSON" "$profile" <<'PY'
import json
import sys
from pathlib import Path

profiles = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["profiles"]
print(profiles[sys.argv[2]]["theme"])
PY
}

validate_layers() {
  local css_file="$1"
  python3 - "$css_file" <<'PY'
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
required = [
    "/* NOVA_CURVE_START */",
    "/* NOVA_CURVE_END */",
    "/* NOVA_HOVER_START */",
    "/* NOVA_HOVER_END */",
]
missing = [marker for marker in required if marker not in text]
if missing:
    raise SystemExit(f"Missing generated markers: {', '.join(missing)}")
if text.count("{") != text.count("}"):
    raise SystemExit("Generated CSS has unbalanced braces.")
PY
}

apply_layers() {
  local theme_file="$1"
  local layers_file="$2"
  python3 - "$theme_file" "$layers_file" <<'PY'
import sys
from pathlib import Path

theme_path = Path(sys.argv[1])
layers_path = Path(sys.argv[2])
theme = theme_path.read_text(encoding="utf-8")
layers = layers_path.read_text(encoding="utf-8")
markers = [
    ("/* NOVA_CURVE_START */", "/* NOVA_CURVE_END */"),
    ("/* NOVA_HOVER_START */", "/* NOVA_HOVER_END */"),
]

def extract(text: str, start: str, end: str) -> str:
    start_i = text.find(start)
    if start_i < 0:
        raise SystemExit(f"Missing marker {start}")
    end_i = text.find(end, start_i)
    if end_i < 0:
        raise SystemExit(f"Missing marker {end}")
    return text[start_i:end_i + len(end)]

def replace(text: str, start: str, end: str, block: str) -> str:
    start_i = text.find(start)
    if start_i < 0:
        raise SystemExit(f"Missing marker {start} in {theme_path}")
    end_i = text.find(end, start_i)
    if end_i < 0:
        raise SystemExit(f"Missing marker {end} in {theme_path}")
    return text[:start_i] + block + text[end_i + len(end):]

for start, end in markers:
    theme = replace(theme, start, end, extract(layers, start, end))

theme_path.write_text(theme, encoding="utf-8")
PY
}

mapfile -t entrypoints < <(find "$SRC_DIR/profiles" -maxdepth 1 -name '*.scss' -type f | sort)
[[ ${#entrypoints[@]} -gt 0 ]] || die "Nenalezeny zadne Sass profily."

for entrypoint in "${entrypoints[@]}"; do
  profile="$(basename -- "$entrypoint" .scss)"
  output="$OUT_DIR/$profile/gnome-shell-layers.css"
  compile_scss "$entrypoint" "$output"
  validate_layers "$output"

  if [[ "$mode" == "--apply" ]]; then
    theme="$(theme_for_profile "$profile")"
    theme_file="$ROOT/core/themes/$theme/gnome-shell/gnome-shell.css"
    [[ -f "$theme_file" ]] || die "Theme CSS neexistuje: $theme_file"
    apply_layers "$theme_file" "$output"
    printf 'Aktualizovano: %s\n' "${theme_file#$ROOT/}"
  else
    printf 'Zkompilovano: %s\n' "${output#$ROOT/}"
  fi
done
