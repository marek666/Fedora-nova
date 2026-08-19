#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

OUT="${1:-$HOME/Fedora-Nova-export-$(date +%Y%m%d-%H%M%S).tar.gz}"
OUT="$(realpath -m "$OUT")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PAYLOAD="$TMP/fedora-nova-export"
mkdir -p "$PAYLOAD/dconf" "$PAYLOAD/state" \
  "$PAYLOAD/custom/themes" "$PAYLOAD/custom/wallpapers" \
  "$PAYLOAD/custom/palettes"

dump() {
  local file="$1" path="$2"
  dconf dump "$path" >"$PAYLOAD/dconf/$file.dconf" || true
}
dump interface /org/gnome/desktop/interface/
dump wm-preferences /org/gnome/desktop/wm/preferences/
dump background /org/gnome/desktop/background/
dump screensaver /org/gnome/desktop/screensaver/
dump shell /org/gnome/shell/
dump user-theme /org/gnome/shell/extensions/user-theme/
dump dash-to-dock /org/gnome/shell/extensions/dash-to-dock/
dump blur-my-shell /org/gnome/shell/extensions/blur-my-shell/

for file in current-profile previous-profile current-dock previous-dock \
            current-motion previous-motion current-curve previous-curve current-icons \
            current-hover previous-hover current-gtk; do
  [[ -f "$NOVA_CONFIG_DIR/$file" ]] &&
    cp "$NOVA_CONFIG_DIR/$file" "$PAYLOAD/state/$file"
done

if [[ -d "$NOVA_CUSTOM_DIR" ]]; then
  cp -a "$NOVA_CUSTOM_DIR" "$PAYLOAD/custom/profiles"
fi
find "$NOVA_THEMES_DIR" -mindepth 1 -maxdepth 1 -type d \
  -name 'Fedora-Nova-Custom-*' -exec cp -a {} "$PAYLOAD/custom/themes/" \;
find "$NOVA_WALLPAPER_DIR" -maxdepth 1 -type f \
  -name 'custom-*.svg' -exec cp -a {} "$PAYLOAD/custom/wallpapers/" \;
find "$NOVA_PTYXIS_DIR" -maxdepth 1 -type f \
  -name 'Fedora Nova Custom *.palette' -exec cp -a {} "$PAYLOAD/custom/palettes/" \;

cat >"$PAYLOAD/manifest.txt" <<EOF
format=fedora-nova-export-v2
version=$NOVA_VERSION
created=$(date --iso-8601=seconds)
profile=$(current_profile)
curve=$(current_curve)
EOF

mkdir -p "$(dirname "$OUT")"
tar -C "$TMP" -czf "$OUT" fedora-nova-export
log "Export vytvořen: $OUT"
