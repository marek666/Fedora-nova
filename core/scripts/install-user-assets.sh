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

# Asset synchronization replaces only the managed built-ins, never source
# themes or Forge/custom themes. Reject aliases back into bundled themes.
SOURCE_THEMES="$(realpath -e -- "$PROJECT_DIR/themes")"
RUNTIME_THEMES="$(realpath -m -- "$THEMES_DEST")"
[[ "$RUNTIME_THEMES/" != "$SOURCE_THEMES/"* && "$SOURCE_THEMES/" != "$RUNTIME_THEMES/"* ]] ||
  die "Uživatelské themes se nesmějí překrývat s bundled themes."

log "Kopíruji themes a assety"
mkdir -p "$THEMES_DEST" "$WALL_DEST" "$PTYXIS_DEST" "$FASTFETCH_DEST" \
  "$NOVA_CONFIG_DIR" "$NOVA_CUSTOM_DIR" "$ICON_DEST"

rm -rf \
  "$THEMES_DEST/Fedora-Nova" \
  "$THEMES_DEST/Fedora-Nova-Tech" \
  "$THEMES_DEST/Fedora-Nova-Clean" \
  "$THEMES_DEST/Fedora-Nova-Midnight" \
  "$THEMES_DEST/Fedora-Nova-Glass-Lite" \
  "$THEMES_DEST/Fedora-Nova-Pulse"

for theme in Fedora-Nova-Tech Fedora-Nova-Clean Fedora-Nova-Midnight Fedora-Nova-Glass-Lite Fedora-Nova-Pulse; do
  cp -a "$PROJECT_DIR/themes/$theme" "$THEMES_DEST/"
  # Only freshly copied built-ins receive owner write permissions. find does
  # not follow symlinks; source modes and custom themes remain untouched.
  find "$THEMES_DEST/$theme" -type d -exec chmod u+rwx -- {} +
  find "$THEMES_DEST/$theme" -type f -exec chmod u+rw -- {} +
done
cp -a "$PROJECT_DIR/assets/wallpapers/." "$WALL_DEST/"
cp -a "$PROJECT_DIR/terminal/ptyxis/." "$PTYXIS_DEST/"
cp -a "$PROJECT_DIR/terminal/fastfetch/fedora-nova.jsonc" "$FASTFETCH_DEST/"
# profiles.json and curves.json are immutable bundled runtime configuration.
# Do not shadow them under XDG_CONFIG_HOME where old copies can outlive an
# upgrade. Existing legacy copies are intentionally left untouched.
cp -a "$PROJECT_DIR/assets/icons/fedora-nova.svg" "$ICON_DEST/"
"$SCRIPT_DIR/install-tela-icons.sh"
"$SCRIPT_DIR/monitor-panel.sh" install

command_exists gtk-update-icon-cache && gtk-update-icon-cache -f -t "$NOVA_DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
