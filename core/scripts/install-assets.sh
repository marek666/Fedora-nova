#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

THEMES_DEST="$NOVA_DATA_HOME/themes"
WALL_DEST="$NOVA_DATA_HOME/backgrounds/fedora-nova"
PTYXIS_DEST="$NOVA_DATA_HOME/org.gnome.Ptyxis/palettes"
FASTFETCH_DEST="$NOVA_CONFIG_HOME/fastfetch"
ICON_DEST="$NOVA_DATA_HOME/icons/hicolor/scalable/apps"
APP_DESKTOP_DEST="$NOVA_DATA_HOME/applications"
BIN_DEST="${HOME}/.local/bin"

log "Kopíruji themes a assety"
mkdir -p "$THEMES_DEST" "$WALL_DEST" "$PTYXIS_DEST" "$FASTFETCH_DEST" \
  "$NOVA_CONFIG_DIR" "$NOVA_CUSTOM_DIR" "$ICON_DEST" "$APP_DESKTOP_DEST" "$BIN_DEST"

rm -rf \
  "$THEMES_DEST/Fedora-Nova" \
  "$THEMES_DEST/Fedora-Nova-Tech" \
  "$THEMES_DEST/Fedora-Nova-Clean" \
  "$THEMES_DEST/Fedora-Nova-Midnight" \
  "$THEMES_DEST/Fedora-Nova-Glass-Lite" \
  "$THEMES_DEST/Fedora-Nova-Pulse"

for theme in Fedora-Nova-Tech Fedora-Nova-Clean Fedora-Nova-Midnight Fedora-Nova-Glass-Lite Fedora-Nova-Pulse; do
  cp -a "$PROJECT_DIR/themes/$theme" "$THEMES_DEST/"
done
cp -a "$PROJECT_DIR/assets/wallpapers/." "$WALL_DEST/"
cp -a "$PROJECT_DIR/terminal/ptyxis/." "$PTYXIS_DEST/"
cp -a "$PROJECT_DIR/terminal/fastfetch/fedora-nova.jsonc" "$FASTFETCH_DEST/"
cp -a "$PROJECT_DIR/config/colors.json" "$NOVA_CONFIG_DIR/"
cp -a "$PROJECT_DIR/config/profiles.json" "$NOVA_CONFIG_DIR/"
cp -a "$PROJECT_DIR/config/curves.json" "$NOVA_CONFIG_DIR/"
cp -a "$PROJECT_DIR/assets/icons/fedora-nova.svg" "$ICON_DEST/"
cp -a "$PROJECT_DIR/applications/fedora-nova-control.desktop" "$APP_DESKTOP_DEST/"
"$SCRIPT_DIR/install-tela-icons.sh"
"$SCRIPT_DIR/monitor-panel.sh" install

cat > "$BIN_DEST/fedora-nova" <<WRAPPER
#!/usr/bin/env bash
exec "$NOVA_APP_DIR/nova" "\$@"
WRAPPER
chmod +x "$BIN_DEST/fedora-nova"

command_exists gtk-update-icon-cache && gtk-update-icon-cache -f -t "$NOVA_DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
command_exists update-desktop-database && update-desktop-database "$APP_DESKTOP_DEST" >/dev/null 2>&1 || true
