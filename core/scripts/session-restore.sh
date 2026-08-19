#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ACTION="${1:-apply}"
QUIET=0
if [[ "${1:-}" == "--quiet" ]]; then
  ACTION=apply
  QUIET=1
  shift
fi
shift || true

while (($#)); do
  case "$1" in
    --quiet) QUIET=1 ;;
    *) die "Použij: $0 {apply|enable|disable|status} [--quiet]" ;;
  esac
  shift
done

launcher_path() {
  printf '%s\n' "$NOVA_CONFIG_DIR/session-restore"
}

write_launcher() {
  local launcher nova_cmd quoted_app quoted_nova
  launcher="$(launcher_path)"
  nova_cmd="$NOVA_APP_DIR/nova"
  if [[ ! -x "$nova_cmd" ]]; then
    nova_cmd="$(command -v fedora-nova || true)"
  fi
  [[ -n "$nova_cmd" && -x "$nova_cmd" ]] ||
    die "Fedora Nova CLI nebylo nalezeno pro autostart."
  mkdir -p "$NOVA_CONFIG_DIR"
  printf -v quoted_app '%q' "$NOVA_APP_DIR"
  printf -v quoted_nova '%q' "$nova_cmd"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'sleep "${FEDORA_NOVA_SESSION_DELAY:-2}"\n'
    printf 'export FEDORA_NOVA_APP_DIR=%s\n' "$quoted_app"
    printf 'exec %s session-restore --quiet\n' "$quoted_nova"
  } > "$launcher"
  chmod +x "$launcher"
}

enable_autostart() {
  local launcher
  write_launcher
  launcher="$(launcher_path)"
  mkdir -p "$NOVA_AUTOSTART_DIR"
  {
    printf '[Desktop Entry]\n'
    printf 'Type=Application\n'
    printf 'Name=Fedora Nova Session Restore\n'
    printf 'Comment=Reapply Fedora Nova desktop theme after login\n'
    printf 'Exec=%s\n' "$launcher"
    printf 'OnlyShowIn=GNOME;\n'
    printf 'X-GNOME-Autostart-enabled=true\n'
    printf 'NoDisplay=true\n'
  } > "$NOVA_SESSION_AUTOSTART"
  log "Automatické obnovení po přihlášení je zapnuté."
}

disable_autostart() {
  rm -f "$NOVA_SESSION_AUTOSTART" "$(launcher_path)"
  log "Automatické obnovení po přihlášení je vypnuté."
}

restore_session() {
  local profile
  profile="$(current_profile)"
  if [[ "$profile" == system ]]; then
    log "Aktivní je systémový profil; Fedora Nova session restore přeskakuji."
    return 0
  fi
  "$SCRIPT_DIR/apply-settings.sh" "$profile" --session-restore
}

status_autostart() {
  printf 'Autostart:  %s\n' "$([[ -f "$NOVA_SESSION_AUTOSTART" ]] && echo yes || echo no)"
  printf 'Desktop:    %s\n' "$NOVA_SESSION_AUTOSTART"
  printf 'Launcher:   %s\n' "$(launcher_path)"
  if [[ -f "$NOVA_SESSION_AUTOSTART" ]]; then
    grep -E '^(Exec|X-GNOME-Autostart-enabled)=' "$NOVA_SESSION_AUTOSTART" || true
  fi
}

case "$ACTION" in
  apply|restore)
    mkdir -p "$NOVA_STATE_DIR"
    if [[ $QUIET -eq 1 ]]; then
      restore_session >> "$NOVA_STATE_DIR/session-restore.log" 2>&1
    else
      restore_session
    fi
    ;;
  enable|on|autostart) enable_autostart ;;
  disable|off) disable_autostart ;;
  status) status_autostart ;;
  *) die "Použij: $0 {apply|enable|disable|status} [--quiet]" ;;
esac
