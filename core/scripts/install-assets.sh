#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Compatibility entrypoint for the legacy standalone installer.
"$SCRIPT_DIR/install-user-assets.sh"

APP_DESKTOP_DEST="$NOVA_DATA_HOME/applications"
BIN_DEST="${HOME}/.local/bin"
mkdir -p "$APP_DESKTOP_DEST" "$BIN_DEST"
cp -a "$PROJECT_DIR/applications/fedora-nova-control.desktop" "$APP_DESKTOP_DEST/"

cat > "$BIN_DEST/fedora-nova" <<WRAPPER
#!/usr/bin/env bash
exec "$NOVA_APP_DIR/nova" "\$@"
WRAPPER
chmod +x "$BIN_DEST/fedora-nova"

command_exists update-desktop-database && update-desktop-database "$APP_DESKTOP_DEST" >/dev/null 2>&1 || true
