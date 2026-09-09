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

resolve_session_cli() {
  local lib core package prefix candidate
  # Bind to the loaded physical runtime, never an inherited APP_DIR or PATH CLI.
  lib="$(realpath -e -- "$SCRIPT_DIR/lib.sh")" ||
    die "Nelze určit fyzický runtime pro autostart."
  core="${lib%/*}"
  core="${core%/*}"
  package="${core%/*}"
  if [[ "$core" == */share/fedora-nova/core ]] && package_layout_present "$package"; then
    prefix="${core%/share/fedora-nova/core}"
    candidate="$prefix/bin/fedora-nova"
    if [[ -f "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return
    fi
  fi
  candidate="$core/nova"
  [[ -f "$candidate" && -x "$candidate" ]] ||
    die "Fedora Nova CLI není spustitelné pro autostart: $candidate"
  printf '%s\n' "$candidate"
}

desktop_exec_path() {
  local value="$1"
  # Exec quoting first, then Desktop Entry string escaping (two distinct layers).
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//\$/\\\$}"
  value="${value//\`/\\\`}"
  value="${value//%/%%}"
  value="${value//\\/\\\\}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\t'/\\t}"
  value="${value//$'\r'/\\r}"
  # '=' is forbidden in the executable token, and GLib checks executable
  # existence before expanding '%%'. For those paths, pass the script as a
  # Bash argument instead; this still uses no shell command string.
  [[ "$1" != *=* && "$1" != *%* ]] || printf '/bin/bash '
  printf '"%s"' "$value"
}

write_launcher() {
  local quoted_nova
  printf -v quoted_nova '%q' "$1"
  printf '#!/usr/bin/env bash\n'
  printf 'sleep "${FEDORA_NOVA_SESSION_DELAY:-2}"\n'
  printf 'unset FEDORA_NOVA_APP_DIR FEDORA_NOVA_CORE FEDORA_NOVA_CLI\n'
  printf 'exec %s session-restore --quiet\n' "$quoted_nova"
}

enable_autostart() (
  local launcher nova_cmd launcher_tmp='' desktop_tmp=''
  # Resolve before creating anything, so an unusable runtime preserves old files.
  nova_cmd="$(resolve_session_cli)" || exit 1
  launcher="$(launcher_path)"
  mkdir -p "$NOVA_CONFIG_DIR" "$NOVA_AUTOSTART_DIR"
  trap 'rm -f -- "$launcher_tmp" "$desktop_tmp"' EXIT
  launcher_tmp="$(mktemp "$NOVA_CONFIG_DIR/.session-restore.XXXXXX")"
  desktop_tmp="$(mktemp "$NOVA_AUTOSTART_DIR/.fedora-nova-session.XXXXXX")"
  write_launcher "$nova_cmd" > "$launcher_tmp"
  chmod 700 "$launcher_tmp"
  {
    printf '[Desktop Entry]\n'
    printf 'Type=Application\n'
    printf 'Name=Fedora Nova Session Restore\n'
    printf 'Comment=Reapply Fedora Nova desktop theme after login\n'
    printf 'Exec=%s\n' "$(desktop_exec_path "$launcher")"
    printf 'OnlyShowIn=GNOME;\n'
    printf 'X-GNOME-Autostart-enabled=true\n'
    printf 'NoDisplay=true\n'
  } > "$desktop_tmp"
  mv -f -- "$launcher_tmp" "$launcher"
  mv -f -- "$desktop_tmp" "$NOVA_SESSION_AUTOSTART"
  log "Automatické obnovení po přihlášení je zapnuté."
)

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
