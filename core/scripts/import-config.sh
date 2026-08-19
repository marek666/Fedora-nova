#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ARCHIVE="${1:-}"
[[ -n "$ARCHIVE" ]] || die "Použij: import-config.sh ARCHIVE.tar.gz"
[[ -f "$ARCHIVE" ]] || die "Soubor neexistuje: $ARCHIVE"
command_exists python3 || die "Chybí python3."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$ARCHIVE" "$TMP" <<'PY'
import sys
import tarfile
from pathlib import Path

archive = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()

with tarfile.open(archive, "r:gz") as tf:
    for member in tf.getmembers():
        target = (destination / member.name).resolve()
        if destination != target and destination not in target.parents:
            raise SystemExit("Archiv obsahuje nebezpečnou cestu.")
        if not (member.isfile() or member.isdir()):
            raise SystemExit("Archiv obsahuje nepovolený typ položky.")
    tf.extractall(destination)
PY

PAYLOAD="$TMP/fedora-nova-export"
[[ -f "$PAYLOAD/manifest.txt" ]] || die "Nejde o Fedora Nova export."

"$SCRIPT_DIR/backup-settings.sh" >/dev/null

load() {
  local file="$1" path="$2"
  [[ -s "$PAYLOAD/dconf/$file.dconf" ]] &&
    dconf load "$path" <"$PAYLOAD/dconf/$file.dconf"
}
load interface /org/gnome/desktop/interface/
load wm-preferences /org/gnome/desktop/wm/preferences/
load background /org/gnome/desktop/background/
load screensaver /org/gnome/desktop/screensaver/
load shell /org/gnome/shell/
load user-theme /org/gnome/shell/extensions/user-theme/
load dash-to-dock /org/gnome/shell/extensions/dash-to-dock/
load blur-my-shell /org/gnome/shell/extensions/blur-my-shell/

mkdir -p "$NOVA_CONFIG_DIR" "$NOVA_CUSTOM_DIR" "$NOVA_THEMES_DIR" \
  "$NOVA_WALLPAPER_DIR" "$NOVA_PTYXIS_DIR"

for file in current-profile previous-profile current-dock previous-dock \
            current-motion previous-motion current-curve previous-curve current-icons \
            current-hover previous-hover current-gtk; do
  [[ -f "$PAYLOAD/state/$file" ]] &&
    cp "$PAYLOAD/state/$file" "$NOVA_CONFIG_DIR/$file"
done

if [[ -d "$PAYLOAD/custom/profiles" ]]; then
  cp -a "$PAYLOAD/custom/profiles/." "$NOVA_CUSTOM_DIR/"
fi
if [[ -d "$PAYLOAD/custom/themes" ]]; then
  cp -a "$PAYLOAD/custom/themes/." "$NOVA_THEMES_DIR/"
fi
if [[ -d "$PAYLOAD/custom/wallpapers" ]]; then
  cp -a "$PAYLOAD/custom/wallpapers/." "$NOVA_WALLPAPER_DIR/"
fi
if [[ -d "$PAYLOAD/custom/palettes" ]]; then
  cp -a "$PAYLOAD/custom/palettes/." "$NOVA_PTYXIS_DIR/"
fi

disable_extension blur-my-shell@aunetx
"$SCRIPT_DIR/apply-hover.sh" "$(current_hover)" >/dev/null 2>&1 || true
"$SCRIPT_DIR/gtk-theme.sh" "$(current_gtk)" >/dev/null 2>&1 || true
log "Import dokončen. Pro jistotu proveď relogin."
