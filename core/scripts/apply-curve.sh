#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

PRESET="${1:-list}"
RELOAD=0
[[ "${2:-}" == "--reload" ]] && RELOAD=1
[[ "${2:-}" == "--no-reload" ]] && RELOAD=0

case "$PRESET" in
  list)
    python3 "$SCRIPT_DIR/curve_style.py" list "$NOVA_APP_DIR/config/curves.json" 2>/dev/null ||
      python3 "$SCRIPT_DIR/curve_style.py" list "$PROJECT_DIR/config/curves.json"
    exit 0
    ;;
  previous)
    PRESET="$(cat "$NOVA_CONFIG_DIR/previous-curve" 2>/dev/null || true)"
    [[ -n "$PRESET" ]] || die "Předchozí curvature preset není uložený."
    ;;
esac

CONFIG="$NOVA_APP_DIR/config/curves.json"
[[ -f "$CONFIG" ]] || CONFIG="$PROJECT_DIR/config/curves.json"
[[ -f "$CONFIG" ]] || die "Chybí curves.json."

python3 "$SCRIPT_DIR/curve_style.py" render "$PRESET" "$CONFIG" >/dev/null ||
  die "Neznámý curvature preset: $PRESET"

mkdir -p "$NOVA_CONFIG_DIR"
CURRENT="$(current_curve)"
if [[ "$CURRENT" != "$PRESET" ]]; then
  printf '%s\n' "$CURRENT" > "$NOVA_CONFIG_DIR/previous-curve"
fi

RESULT="$(
  python3 "$SCRIPT_DIR/curve_style.py" apply "$PRESET" "$CONFIG" \
    "$PROJECT_DIR/themes" "$NOVA_APP_DIR/themes" "$NOVA_THEMES_DIR"
)"
CHANGED="${RESULT%%$'\t'*}"
TOTAL="${RESULT##*$'\t'}"

printf '%s\n' "$PRESET" > "$NOVA_CONFIG_DIR/current-curve"
disable_extension blur-my-shell@aunetx
log "Křivky: $PRESET — upraveno $CHANGED z $TOTAL theme souborů."

if [[ $RELOAD -eq 1 ]]; then
  "$SCRIPT_DIR/reload-theme.sh" || true
fi
