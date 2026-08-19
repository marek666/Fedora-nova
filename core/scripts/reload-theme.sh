#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
UUID=user-theme@gnome-shell-extensions.gcampax.github.com

command_exists gnome-extensions || die "Chybí gnome-extensions."
if ! gnome-extensions info "$UUID" >/dev/null 2>&1; then
  die "User Themes extension není dostupné."
fi

log "Zkouším znovu načíst Shell theme bez odhlášení"
gnome-extensions disable "$UUID" >/dev/null 2>&1 || true
sleep 0.6
gnome-extensions enable "$UUID" >/dev/null 2>&1 || true
sleep 0.4
log "Reload dokončen. Některé prvky GNOME mohou stále vyžadovat relogin."
