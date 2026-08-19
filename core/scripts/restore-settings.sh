#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" && -f "$NOVA_STATE_DIR/latest-backup" ]]; then
  BACKUP_DIR="$(cat "$NOVA_STATE_DIR/latest-backup")"
fi
[[ -n "$BACKUP_DIR" ]] || die "Nebyla nalezena cesta k záloze."
[[ -d "$BACKUP_DIR" ]] || die "Záloha neexistuje: $BACKUP_DIR"
command_exists dconf || die "Chybí příkaz dconf."

log "Obnovuji GNOME nastavení ze $BACKUP_DIR"
load_file() {
  local file="$1" path="$2"
  if [[ -s "$BACKUP_DIR/$file.dconf" ]]; then
    dconf load "$path" < "$BACKUP_DIR/$file.dconf"
    printf '  restored %s\n' "$path"
  fi
}
load_file interface /org/gnome/desktop/interface/
load_file wm-preferences /org/gnome/desktop/wm/preferences/
load_file background /org/gnome/desktop/background/
load_file screensaver /org/gnome/desktop/screensaver/
load_file shell /org/gnome/shell/
load_file user-theme /org/gnome/shell/extensions/user-theme/
load_file dash-to-dock /org/gnome/shell/extensions/dash-to-dock/
load_file blur-my-shell /org/gnome/shell/extensions/blur-my-shell/

mkdir -p "$NOVA_CONFIG_DIR"
for f in current-profile previous-profile current-dock previous-dock current-motion previous-motion current-curve previous-curve current-icons current-hover previous-hover current-gtk; do
  [[ -f "$BACKUP_DIR/$f" ]] && cp "$BACKUP_DIR/$f" "$NOVA_CONFIG_DIR/$f"
done
disable_extension blur-my-shell@aunetx
"$SCRIPT_DIR/apply-hover.sh" "$(current_hover)" >/dev/null 2>&1 || true
"$SCRIPT_DIR/gtk-theme.sh" "$(current_gtk)" >/dev/null 2>&1 || true
log "Obnova dokončena. Pro plný efekt se odhlas a znovu přihlas."
