#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_DIR/scripts/lib.sh"

RESTORE=0
REMOVE_PACKAGES=0
usage() {
  cat <<'USAGE'
Usage: ./uninstall.sh [--restore] [--remove-packages]

  --restore          obnoví poslední dconf zálohu
  --remove-packages  odinstaluje i balíčky Fedora Nova
USAGE
}
while (($#)); do
  case "$1" in
    --restore) RESTORE=1 ;;
    --remove-packages) REMOVE_PACKAGES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Neznámá volba: $1" ;;
  esac
  shift
done

log "Vypínám Fedora Nova theme a dock"
disable_extension blur-my-shell@aunetx
disable_extension dash-to-dock@micxgx.gmail.com
disable_extension user-theme@gnome-shell-extensions.gcampax.github.com
disable_extension topbar-all-monitors@fa8i.github.io
"$PROJECT_DIR/scripts/gtk-theme.sh" off >/dev/null 2>&1 || true
"$PROJECT_DIR/scripts/steam-icons.sh" restore >/dev/null 2>&1 || true

if [[ $RESTORE -eq 1 ]]; then
  "$PROJECT_DIR/scripts/restore-settings.sh"
else
  warn "Nastavení nebyla obnovena. Použij --restore pro návrat k poslední záloze."
fi

find "$NOVA_THEMES_DIR" -mindepth 1 -maxdepth 1 -type d \
  -name 'Fedora-Nova-Custom-*' -exec rm -rf -- {} + 2>/dev/null || true
find "$NOVA_PTYXIS_DIR" -maxdepth 1 -type f \
  -name 'Fedora Nova Custom *.palette' -delete 2>/dev/null || true

rm -rf \
  "$NOVA_DATA_HOME/themes/Fedora-Nova" \
  "$NOVA_DATA_HOME/themes/Fedora-Nova-Tech" \
  "$NOVA_DATA_HOME/themes/Fedora-Nova-Clean" \
  "$NOVA_DATA_HOME/themes/Fedora-Nova-Midnight" \
  "$NOVA_DATA_HOME/themes/Fedora-Nova-Glass-Lite" \
  "$NOVA_DATA_HOME/themes/Fedora-Nova-Pulse" \
  "$NOVA_DATA_HOME/backgrounds/fedora-nova" \
  "$NOVA_DATA_HOME/icons/Tela-circle" \
  "$NOVA_DATA_HOME/icons/Tela-circle-dark" \
  "$NOVA_DATA_HOME/icons/Tela-circle-light" \
  "$NOVA_DATA_HOME/icons/Fedora-Nova-Steam" \
  "$NOVA_DATA_HOME/gnome-shell/extensions/topbar-all-monitors@fa8i.github.io" \
  "$NOVA_CONFIG_DIR"
rm -f \
  "$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes/Fedora Nova.palette" \
  "$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes/Fedora Nova Tech.palette" \
  "$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes/Fedora Nova Clean.palette" \
  "$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes/Fedora Nova Midnight.palette" \
  "$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes/Fedora Nova Glass Lite.palette" \
  "$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes/Fedora Nova Pulse.palette" \
  "$NOVA_CONFIG_HOME/fastfetch/fedora-nova.jsonc" \
  "$NOVA_DATA_HOME/icons/hicolor/scalable/apps/fedora-nova.svg" \
  "$NOVA_DATA_HOME/applications/fedora-nova-control.desktop" \
  "$HOME/.local/bin/fedora-nova"

APP_DEST="$NOVA_DATA_HOME/fedora-nova"
if [[ "$PROJECT_DIR" != "$APP_DEST" ]]; then
  rm -rf "$APP_DEST"
else
  (sleep 1; rm -rf "$APP_DEST") >/dev/null 2>&1 &
fi

if [[ $REMOVE_PACKAGES -eq 1 ]]; then
  mapfile -t PACKAGES < <(grep -Ev '^[[:space:]]*(#|$)' "$PROJECT_DIR/config/packages.txt")
  sudo dnf remove -y "${PACKAGES[@]}"
fi

log "Odinstalace dokončena. Pro úplné překreslení proveď relogin."
