#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

ACTION="${1:-status}"
GTK4_FILE="$NOVA_CONFIG_HOME/gtk-4.0/gtk.css"
GTK3_FILE="$NOVA_CONFIG_HOME/gtk-3.0/gtk.css"
BEGIN='/* NOVA_GTK_START */'
END='/* NOVA_GTK_END */'

profile_json() {
  python3 "$SCRIPT_DIR/profile-info.py" json "$(current_profile)" \
    "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR"
}

modify_file() {
  local file="$1" block_file="$2" mode="$3"
  mkdir -p "$(dirname "$file")"
  python3 - "$file" "$block_file" "$mode" <<'PY'
import re, sys
from pathlib import Path
file = Path(sys.argv[1])
block_file = Path(sys.argv[2])
mode = sys.argv[3]
begin = '/* NOVA_GTK_START */'
end = '/* NOVA_GTK_END */'
text = file.read_text(encoding='utf-8') if file.exists() else ''
text = re.sub(re.escape(begin) + r'.*?' + re.escape(end), '', text, flags=re.S).rstrip()
if mode == 'on':
    block = block_file.read_text(encoding='utf-8').strip()
    text = (text + '\n\n' + block).strip()
file.write_text(text + ('\n' if text else ''), encoding='utf-8')
PY
}

generate_blocks() {
  local tmpdir json
  tmpdir="$(mktemp -d)"
  json="$tmpdir/profile.json"
  profile_json > "$json"
  python3 - "$json" "$tmpdir/gtk4.css" "$tmpdir/gtk3.css" <<'PY'
import json, sys
from pathlib import Path
p = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))

def c(name, fallback):
    return str(p.get(name, fallback))
accent = c('accent', '#2ED8E8')
accent_fg = c('accent_fg', '#06131A')
text = c('text', '#F8EFFF')
bg = c('bg', '#08091B')
panel = c('panel', '#050817')
large = c('large', '#120C25')
surface = c('surface', '#21133A')
surface2 = c('surface2', '#2B1749')
card = c('card', '#2A1C3D')
border = c('border', '#60406E')

block4 = f'''/* NOVA_GTK_START */
/* Fedora Nova GTK/libadwaita color layer. Remove with: fedora-nova gtk off */
:root {{
  --accent-bg-color: {accent};
  --accent-fg-color: {accent_fg};
  --window-bg-color: {bg};
  --window-fg-color: {text};
  --view-bg-color: {large};
  --view-fg-color: {text};
  --headerbar-bg-color: {surface};
  --headerbar-fg-color: {text};
  --headerbar-backdrop-color: {large};
  --sidebar-bg-color: {card};
  --sidebar-fg-color: {text};
  --sidebar-backdrop-color: {surface};
  --secondary-sidebar-bg-color: {surface};
  --secondary-sidebar-fg-color: {text};
  --secondary-sidebar-backdrop-color: {large};
  --card-bg-color: {surface};
  --card-fg-color: {text};
  --dialog-bg-color: {large};
  --dialog-fg-color: {text};
  --popover-bg-color: {surface};
  --popover-fg-color: {text};
  --overview-bg-color: {bg};
  --overview-fg-color: {text};
  --thumbnail-bg-color: {surface2};
  --thumbnail-fg-color: {text};
}}

/* Conservative geometry: colors first, only common cards get Nova curvature. */
.card,
.boxed-list,
.boxed-list-separate > row,
popover > contents,
entry,
button {{
  border-radius: 16px;
}}
/* NOVA_GTK_END */'''

block3 = f'''/* NOVA_GTK_START */
/* Fedora Nova GTK3 compatibility layer. */
@define-color theme_bg_color {bg};
@define-color theme_fg_color {text};
@define-color theme_base_color {large};
@define-color theme_text_color {text};
@define-color selected_bg_color {accent};
@define-color selected_fg_color {accent_fg};
@define-color insensitive_bg_color {surface};
@define-color insensitive_fg_color {text};
@define-color borders {border};

window,
.background {{
  background-color: @theme_bg_color;
  color: @theme_fg_color;
}}
headerbar,
.titlebar {{
  background-color: {surface};
  color: {text};
  border-color: {border};
}}
.sidebar,
.navigation-sidebar {{
  background-color: {card};
  color: {text};
}}
/* NOVA_GTK_END */'''
Path(sys.argv[2]).write_text(block4 + '\n', encoding='utf-8')
Path(sys.argv[3]).write_text(block3 + '\n', encoding='utf-8')
PY
  printf '%s\n' "$tmpdir"
}

case "$ACTION" in
  on|refresh)
    TMP="$(generate_blocks)"
    trap 'rm -rf "$TMP"' EXIT
    modify_file "$GTK4_FILE" "$TMP/gtk4.css" on
    modify_file "$GTK3_FILE" "$TMP/gtk3.css" on
    mkdir -p "$NOVA_CONFIG_DIR"
    printf 'on\n' > "$NOVA_CONFIG_DIR/current-gtk"
    log "Nova GTK barvy zapnuté. Zavři a znovu otevři Soubory, Textový editor a Nastavení."
    ;;
  off)
    EMPTY="$(mktemp)"
    trap 'rm -f "$EMPTY"' EXIT
    modify_file "$GTK4_FILE" "$EMPTY" off
    modify_file "$GTK3_FILE" "$EMPTY" off
    mkdir -p "$NOVA_CONFIG_DIR"
    printf 'off\n' > "$NOVA_CONFIG_DIR/current-gtk"
    log "Nova GTK barvy vypnuté. Aplikace je potřeba znovu otevřít."
    ;;
  status)
    printf 'State:      %s\n' "$(current_gtk)"
    printf 'GTK4 file:  %s\n' "$GTK4_FILE"
    printf 'GTK3 file:  %s\n' "$GTK3_FILE"
    grep -Fq "$BEGIN" "$GTK4_FILE" 2>/dev/null && printf 'GTK4 layer: yes\n' || printf 'GTK4 layer: no\n'
    grep -Fq "$BEGIN" "$GTK3_FILE" 2>/dev/null && printf 'GTK3 layer: yes\n' || printf 'GTK3 layer: no\n'
    ;;
  *) die "Použij: $0 {on|off|refresh|status}" ;;
esac
