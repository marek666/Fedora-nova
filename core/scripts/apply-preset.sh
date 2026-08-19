#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

usage() {
  cat <<'USAGE'
Použij: apply-preset.sh {list|full} [PROFILE] [--reload] [--no-autostart] [--no-backup] [--skip-assets]

  full   kompletní Nova desktop: User Themes, Dash to Dock, Top Bar All
         Monitors, Continuous Squircle, Circle Large hover, Tela Circle
         + kruhové Steam ikony, Nova GTK/libadwaita barvy a autostart
USAGE
}

PRESET="${1:-list}"
if [[ $# -gt 0 ]]; then
  shift
fi

PROFILE=""
RELOAD=0
AUTOSTART=1
BACKUP=1
ASSETS=1

while (($#)); do
  case "$1" in
    --profile)
      shift
      (($#)) || die "Za --profile chybí název profilu."
      PROFILE="$1"
      ;;
    --reload) RELOAD=1 ;;
    --no-autostart) AUTOSTART=0 ;;
    --no-backup) BACKUP=0 ;;
    --skip-assets) ASSETS=0 ;;
    -h|--help) usage; exit 0 ;;
    --*) die "Neznámá volba: $1" ;;
    *)
      [[ -z "$PROFILE" ]] || die "Profil je zadaný víckrát."
      PROFILE="$1"
      ;;
  esac
  shift
done

profile_config() {
  if [[ -f "$NOVA_APP_DIR/config/profiles.json" ]]; then
    printf '%s\n' "$NOVA_APP_DIR/config/profiles.json"
  else
    printf '%s\n' "$PROJECT_DIR/config/profiles.json"
  fi
}

validate_profile() {
  local profile="$1"
  python3 "$SCRIPT_DIR/profile-info.py" shell "$profile" \
    "$(profile_config)" "$NOVA_CUSTOM_DIR" >/dev/null
}

apply_full() {
  if [[ -z "$PROFILE" ]]; then
    PROFILE="$(current_profile)"
  fi
  if [[ "$PROFILE" == system ]]; then
    PROFILE=tech
  fi

  ensure_gnome_session
  validate_profile "$PROFILE" || die "Neznámý profil: $PROFILE"

  mkdir -p "$NOVA_CONFIG_DIR"
  printf '%s\n' "$PROFILE" > "$NOVA_CONFIG_DIR/current-profile"
  printf 'balanced\n' > "$NOVA_CONFIG_DIR/current-dock"
  printf 'balanced\n' > "$NOVA_CONFIG_DIR/current-motion"
  printf 'squircle\n' > "$NOVA_CONFIG_DIR/current-curve"
  printf 'circle\n' > "$NOVA_CONFIG_DIR/current-hover"
  printf 'tela-steam\n' > "$NOVA_CONFIG_DIR/current-icons"
  printf 'on\n' > "$NOVA_CONFIG_DIR/current-gtk"

  if [[ $BACKUP -eq 1 && -z "${FEDORA_NOVA_SKIP_BACKUP:-}" ]]; then
    if command_exists dconf; then
      "$SCRIPT_DIR/backup-settings.sh" >/dev/null || warn "Záloha dconf se nepovedla; pokračuji."
    else
      warn "dconf není dostupné; přeskakuji zálohu."
    fi
  fi

  if [[ $ASSETS -eq 1 ]]; then
    log "Instaluji lokální Nova assety a bundled rozšíření"
    "$SCRIPT_DIR/install-assets.sh"
  fi

  log "Aplikuji kompletní Nova setup"
  "$SCRIPT_DIR/apply-settings.sh" "$PROFILE"

  if [[ $AUTOSTART -eq 1 ]]; then
    "$SCRIPT_DIR/session-restore.sh" enable
  fi

  if [[ $RELOAD -eq 1 ]]; then
    "$SCRIPT_DIR/reload-theme.sh" || true
  fi

  log "Kompletní Nova setup je hotový a uložený pro další přihlášení."
}

case "$PRESET" in
  list)
    printf '%-12s %s\n' full 'kompletní persistentní Nova desktop'
    ;;
  full|nova-full|mutter)
    apply_full
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage >&2
    die "Neznámý preset: $PRESET"
    ;;
esac
