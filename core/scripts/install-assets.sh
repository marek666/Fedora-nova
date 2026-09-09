#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Compatibility entrypoint for the legacy standalone core installer.
# Runtime/user assets are installed first; the only remaining integration
# artifact is the standalone CLI wrapper. The legacy Settings desktop entry
# has been retired in favor of the modern production frontend.
BIN_DEST="${HOME}/.local/bin"
WRAPPER="$BIN_DEST/fedora-nova"
TARGET="$NOVA_APP_DIR/nova"

[[ -f "$TARGET" && -x "$TARGET" ]] || die "Legacy CLI target není spustitelný: $TARGET"

# Ownership preflight must happen before user assets are touched. A canonical
# package installed into ~/.local uses the same bin path, so never overwrite
# an unknown, symlinked, or package-owned fedora-nova executable here.
if [[ -e "$WRAPPER" || -L "$WRAPPER" ]]; then
  is_managed_legacy_cli_wrapper "$WRAPPER" ||
    die "Odmítám přepsat $WRAPPER: není to rozpoznaný Fedora Nova legacy standalone wrapper. Použij canonical package instalaci nebo nejdřív odstraň konflikt ručně."
fi

"$SCRIPT_DIR/install-user-assets.sh"
write_legacy_cli_wrapper "$WRAPPER" "$TARGET"
