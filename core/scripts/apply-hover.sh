#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

MODE="${1:-list}"
RELOAD=0
[[ "${2:-}" == "--reload" ]] && RELOAD=1

case "$MODE" in
  list)
    printf '%-15s %s\n' circle 'větší kruhový halo pouze pod ikonou; výchozí'
    printf '%-15s %s\n' circle-compact 'menší kruhový hover pro kompaktní vzhled'
    printf '%-15s %s\n' tile 'barevný squircle kolem celé dlaždice ikony a názvu'
    printf '%-15s %s\n' none 'bez hover podložky'
    exit 0
    ;;
  previous)
    MODE="$(cat "$NOVA_CONFIG_DIR/previous-hover" 2>/dev/null || true)"
    [[ -n "$MODE" ]] || die "Předchozí hover režim není uložený."
    ;;
  circle|circle-compact|tile|none) ;;
  *) die "Použij: $0 {list|circle|circle-compact|tile|none|previous} [--reload]" ;;
esac

mkdir -p "$NOVA_CONFIG_DIR"
CURRENT="$(current_hover)"
if [[ "$CURRENT" != "$MODE" ]]; then
  printf '%s\n' "$CURRENT" > "$NOVA_CONFIG_DIR/previous-hover"
fi

RESULT="$(python3 "$SCRIPT_DIR/hover_style.py" "$MODE" \
  "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" \
  "$PROJECT_DIR/themes" "$NOVA_APP_DIR/themes" "$NOVA_THEMES_DIR")"
printf '%s\n' "$MODE" > "$NOVA_CONFIG_DIR/current-hover"
disable_extension blur-my-shell@aunetx
log "Hover: $MODE — ${RESULT%%$'\t'*} theme souborů upraveno."

if [[ $RELOAD -eq 1 ]]; then
  "$SCRIPT_DIR/reload-theme.sh" || true
fi
