#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

log "Vypínám rozšíření, která mohou měnit compositor nebo Shell"
disable_extension blur-my-shell@aunetx
disable_extension dash-to-dock@micxgx.gmail.com
disable_extension user-theme@gnome-shell-extensions.gcampax.github.com
"$SCRIPT_DIR/session-restore.sh" disable >/dev/null 2>&1 || true
log "Nouzový režim aktivován. Odhlas se a znovu přihlas."
