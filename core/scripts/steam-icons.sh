#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ACTION="${1:-status}"
QUIET=0
[[ "${2:-}" == "--quiet" ]] && QUIET=1
THEME_ROOT="$NOVA_DATA_HOME/icons/Fedora-Nova-Steam"
STATE_ROOT="$NOVA_STATE_DIR/steam-icons"

case "$ACTION" in
  round)
    python3 -c 'from PIL import Image' 2>/dev/null || die "Chybí python3-pillow. Spusť: sudo dnf install python3-pillow"
    if command_exists gsettings; then
      CURRENT_THEME="$(gsettings get org.gnome.desktop.interface icon-theme 2>/dev/null | tr -d "'" || true)"
    else
      CURRENT_THEME=""
    fi
    [[ -n "$CURRENT_THEME" && "$CURRENT_THEME" != "Fedora-Nova-Steam" ]] || \
      CURRENT_THEME="$(cat "$STATE_ROOT/base-theme" 2>/dev/null || echo Tela-circle)"
    PROFILE_JSON="$(python3 "$SCRIPT_DIR/profile-info.py" json "$(current_profile)" \
      "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR")"
    read -r ACCENT BACKGROUND < <(python3 -c \
      'import json,sys; p=json.load(sys.stdin); print(p.get("accent","#2ED8E8"), p.get("large","#120C25"))' \
      <<<"$PROFILE_JSON")
    mkdir -p "$STATE_ROOT"
    set +e
    OUTPUT="$(python3 "$SCRIPT_DIR/steam-icons.py" "$CURRENT_THEME" "$ACCENT" "$BACKGROUND" 2>&1)"
    CODE=$?
    set -e
    if [[ $CODE -eq 0 ]]; then
      try_set org.gnome.desktop.interface icon-theme "'Fedora-Nova-Steam'"
      printf 'tela-steam\n' > "$NOVA_CONFIG_DIR/current-icons"
      [[ $QUIET -eq 1 ]] || printf '%s\n' "$OUTPUT"
      log "Steam herní ikony byly zabaleny do kruhové Fedora Nova vrstvy."
    elif [[ $CODE -eq 4 ]]; then
      [[ $QUIET -eq 1 ]] || printf '%s\n' "$OUTPUT"
      log "Nebyla nalezena žádná použitelná Steam herní zkratka; icon theme se nemění."
    else
      printf '%s\n' "$OUTPUT" >&2
      exit "$CODE"
    fi
    ;;
  restore)
    BASE="$(cat "$STATE_ROOT/base-theme" 2>/dev/null || echo Tela-circle)"
    try_set org.gnome.desktop.interface icon-theme "'$BASE'"
    python3 "$SCRIPT_DIR/steam-icons.py" "$BASE" '#2ED8E8' '#120C25' --restore-desktops >/dev/null 2>&1 || true
    rm -rf "$THEME_ROOT"
    printf 'tela\n' > "$NOVA_CONFIG_DIR/current-icons"
    log "Obnoven icon theme i původní Icon= hodnoty launcherů: $BASE"
    ;;
  status)
    BASE="$(cat "$STATE_ROOT/base-theme" 2>/dev/null || echo —)"
    ACTIVE="$(gsettings get org.gnome.desktop.interface icon-theme 2>/dev/null || echo unavailable)"
    COUNT="$(find "$THEME_ROOT" -type f -path '*/apps/*.png' 2>/dev/null | wc -l)"
    printf 'Active:     %s\n' "$ACTIVE"
    printf 'Base theme: %s\n' "$BASE"
    printf 'Generated:  %s PNG files\n' "$COUNT"
    ;;
  *) die "Použij: $0 {round|restore|status} [--quiet]" ;;
esac
