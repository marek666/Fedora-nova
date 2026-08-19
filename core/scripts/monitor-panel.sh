#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

UUID="topbar-all-monitors@fa8i.github.io"
SOURCE="$PROJECT_DIR/third-party/topbar-all-monitors/$UUID"
DEST="$NOVA_DATA_HOME/gnome-shell/extensions/$UUID"

shell_major() {
  gnome-shell --version 2>/dev/null | grep -oE '[0-9]+' | head -n1 || true
}

add_enabled_gsettings() {
  schema_exists org.gnome.shell || return 0
  python3 - "$UUID" <<'PY' | xargs -0 -r gsettings set org.gnome.shell enabled-extensions
import ast, subprocess, sys
uuid = sys.argv[1]
try:
    raw = subprocess.check_output(
        ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
        text=True,
    ).strip()
    values = ast.literal_eval(raw)
except Exception:
    values = []
if uuid not in values:
    values.append(uuid)
value = "[" + ", ".join(repr(v) for v in values) + "]"
sys.stdout.buffer.write(value.encode() + b"\0")
PY
}

remove_enabled_gsettings() {
  schema_exists org.gnome.shell || return 0
  python3 - "$UUID" <<'PY' | xargs -0 -r gsettings set org.gnome.shell enabled-extensions
import ast, subprocess, sys
uuid = sys.argv[1]
try:
    raw = subprocess.check_output(
        ["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
        text=True,
    ).strip()
    values = ast.literal_eval(raw)
except Exception:
    values = []
values = [v for v in values if v != uuid]
value = "[" + ", ".join(repr(v) for v in values) + "]"
sys.stdout.buffer.write(value.encode() + b"\0")
PY
}

install_extension() {
  [[ -d "$SOURCE" ]] || die "Chybí bundled Top Bar All Monitors."
  if [[ -d "$DEST" && "${1:-}" != force ]]; then
    log "Top Bar All Monitors už je nainstalovaný; existující kopii zachovávám."
    return 0
  fi
  mkdir -p "$(dirname "$DEST")"
  rm -rf "$DEST"
  cp -a "$SOURCE" "$DEST"
  log "Top Bar All Monitors byl nainstalován do $DEST."
}

enable_panel() {
  local major
  major="$(shell_major)"
  if [[ -n "$major" && "$major" != 50 ]]; then
    warn "Top Bar All Monitors je určený pro GNOME Shell 50; zjištěno $major. Nezapínám."
    return 0
  fi
  if [[ "${XDG_SESSION_TYPE:-wayland}" != wayland ]]; then
    warn "Rozšíření je určeno pro Wayland; aktuální session: ${XDG_SESSION_TYPE:-unknown}."
  fi
  if command_exists gnome-extensions && gnome-extensions info "$UUID" >/dev/null 2>&1; then
    gnome-extensions enable "$UUID" >/dev/null 2>&1 || true
  fi
  add_enabled_gsettings
  log "Top panel na sekundárních monitorech je povolený. Po první instalaci může být nutný relogin."
}

disable_panel() {
  if command_exists gnome-extensions; then
    gnome-extensions disable "$UUID" >/dev/null 2>&1 || true
  fi
  remove_enabled_gsettings
  log "Top panel na sekundárních monitorech je vypnutý."
}

status_panel() {
  printf 'UUID:       %s\n' "$UUID"
  printf 'Installed:  %s\n' "$([[ -d "$DEST" ]] && echo yes || echo no)"
  if command_exists gnome-extensions && gnome-extensions list --enabled 2>/dev/null | grep -Fxq "$UUID"; then
    enabled=yes
  elif gsettings get org.gnome.shell enabled-extensions 2>/dev/null | grep -Fq "$UUID"; then
    enabled=pending-or-enabled
  else
    enabled=no
  fi
  printf 'Enabled:    %s\n' "$enabled"
  printf 'GNOME:      %s\n' "$(gnome-shell --version 2>/dev/null || echo unavailable)"
  printf 'Session:    %s\n' "${XDG_SESSION_TYPE:-unknown}"
}

case "${1:-status}" in
  install) install_extension ;;
  refresh) install_extension force ;;
  on|enable) install_extension; enable_panel ;;
  off|disable) disable_panel ;;
  status) status_panel ;;
  *) die "Použij: monitor-panel.sh {install|refresh|on|off|status}" ;;
esac
