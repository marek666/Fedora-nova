#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Compatibility entrypoint for the legacy standalone core installer.
# Runtime/user assets are installed first; the only remaining integration
# artifact is the standalone CLI wrapper. The legacy Settings desktop entry
# has been retired in favor of the modern production frontend.
"$SCRIPT_DIR/install-user-assets.sh"

BIN_DEST="${HOME}/.local/bin"
mkdir -p "$BIN_DEST"

cat > "$BIN_DEST/fedora-nova" <<WRAPPER
#!/usr/bin/env bash
exec "$NOVA_APP_DIR/nova" "\$@"
WRAPPER
chmod +x "$BIN_DEST/fedora-nova"
