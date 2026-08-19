#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

command_exists dconf || die "Chybí příkaz dconf."
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$NOVA_STATE_DIR/backups/$STAMP"
mkdir -p "$BACKUP_DIR"

log "Zálohuji dotčená GNOME nastavení do $BACKUP_DIR"
dump_path() {
  local name="$1" path="$2"
  dconf dump "$path" > "$BACKUP_DIR/$name.dconf" || true
}
dump_path interface /org/gnome/desktop/interface/
dump_path wm-preferences /org/gnome/desktop/wm/preferences/
dump_path background /org/gnome/desktop/background/
dump_path screensaver /org/gnome/desktop/screensaver/
dump_path shell /org/gnome/shell/
dump_path user-theme /org/gnome/shell/extensions/user-theme/
dump_path dash-to-dock /org/gnome/shell/extensions/dash-to-dock/
dump_path blur-my-shell /org/gnome/shell/extensions/blur-my-shell/

for f in current-profile previous-profile current-dock previous-dock current-motion previous-motion current-curve previous-curve current-icons current-hover previous-hover current-gtk; do
  [[ -f "$NOVA_CONFIG_DIR/$f" ]] && cp "$NOVA_CONFIG_DIR/$f" "$BACKUP_DIR/$f"
done

printf '%s\n' "$BACKUP_DIR" > "$NOVA_STATE_DIR/latest-backup"
printf '%s\n' "$BACKUP_DIR"
