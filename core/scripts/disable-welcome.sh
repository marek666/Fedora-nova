#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ACTION="${1:-off}"

shell_version() {
  local version=""
  if command_exists gnome-shell; then
    version="$(gnome-shell --version 2>/dev/null | awk '{print $NF}' || true)"
  fi
  if [[ -z "$version" ]]; then
    version="$(gsettings get org.gnome.shell welcome-dialog-last-shown-version 2>/dev/null | tr -d "'" || true)"
  fi
  printf '%s\n' "${version:-999.0}"
}

disable_autostart() {
  local desktop_id="$1"
  local target="$NOVA_AUTOSTART_DIR/$desktop_id"
  mkdir -p "$NOVA_AUTOSTART_DIR"
  cat > "$target" <<EOF
[Desktop Entry]
Type=Application
Name=${desktop_id%.desktop}
Hidden=true
EOF
}

is_shell_welcome_done() {
  local current shown
  current="$(shell_version)"
  shown="$(gsettings get org.gnome.shell welcome-dialog-last-shown-version 2>/dev/null | tr -d "'" || true)"
  [[ -n "$shown" && "$shown" == "$current" ]]
}

case "$ACTION" in
  off|disable)
    if key_exists org.gnome.shell welcome-dialog-last-shown-version; then
      try_set org.gnome.shell welcome-dialog-last-shown-version "'$(shell_version)'"
    fi

    mkdir -p "$NOVA_CONFIG_HOME"
    : > "$NOVA_CONFIG_HOME/gnome-initial-setup-done"

    for desktop_id in \
      org.gnome.Tour.desktop \
      gnome-tour.desktop \
      gnome-initial-setup.desktop \
      gnome-initial-setup-first-login.desktop \
      fedora-welcome.desktop \
      org.fedoraproject.Welcome.desktop; do
      disable_autostart "$desktop_id"
    done

    log "Uvítací okna GNOME/Fedora jsou označená jako vyřízená."
    ;;
  status)
    if is_shell_welcome_done; then
      printf 'GNOME welcome: hotovo\n'
    else
      printf 'GNOME welcome: může se znovu zobrazit\n'
    fi
    if [[ -f "$NOVA_CONFIG_HOME/gnome-initial-setup-done" ]]; then
      printf 'Initial setup:  hotovo\n'
    else
      printf 'Initial setup:  není označený jako hotový\n'
    fi
    if [[ -f "$NOVA_AUTOSTART_DIR/org.gnome.Tour.desktop" ]]; then
      printf 'Tour autostart: vypnutý\n'
    else
      printf 'Tour autostart: bez uživatelského override\n'
    fi
    ;;
  *)
    die "Použij: $0 {off|disable|status}"
    ;;
esac
