#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

choice="${1:-list}"
case "$choice" in
  list)
    printf '%-12s %s\n' tela 'Tela-circle (výchozí Fedora Nova 0.6)'
    printf '%-12s %s\n' tela-dark 'Tela-circle-dark'
    printf '%-12s %s\n' tela-light 'Tela-circle-light'
    printf '%-12s %s\n' tela-steam 'Tela Circle + kruhové Steam herní ikony'
    printf '%-12s %s\n' papirus 'Papirus-Dark'
    printf '%-12s %s\n' adwaita 'Adwaita (čistý GNOME vzhled)'
    exit 0
    ;;
  tela) theme='Tela-circle' ;;
  tela-dark) theme='Tela-circle-dark' ;;
  tela-light) theme='Tela-circle-light' ;;
  tela-steam)
    "$SCRIPT_DIR/apply-icons.sh" tela
    "$SCRIPT_DIR/steam-icons.sh" round
    exit 0
    ;;
  papirus) theme='Papirus-Dark' ;;
  adwaita) theme='Adwaita' ;;
  *) die "Použij: $0 {list|tela|tela-dark|tela-light|tela-steam|papirus|adwaita}" ;;
esac

icons_root="$NOVA_DATA_HOME/icons"
if [[ ! -d "/usr/share/icons/$theme" && ! -d "$icons_root/$theme" ]]; then
  if [[ "$choice" == tela* ]]; then
    "$SCRIPT_DIR/install-tela-icons.sh"
  else
    die "Icon theme $theme není nainstalované."
  fi
fi
try_set org.gnome.desktop.interface icon-theme "'$theme'"
mkdir -p "$NOVA_CONFIG_DIR"
printf '%s\n' "$choice" > "$NOVA_CONFIG_DIR/current-icons"
log "Icon theme: $theme"
