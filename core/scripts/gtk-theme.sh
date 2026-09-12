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
/* Fedora Nova GTK3 compatibility layer.
 * Keep classic GTK3 applications coherent without replacing the system theme.
 */
@define-color theme_bg_color {bg};
@define-color theme_fg_color {text};
@define-color theme_base_color {large};
@define-color theme_text_color {text};
@define-color theme_selected_bg_color {accent};
@define-color theme_selected_fg_color {accent_fg};
@define-color selected_bg_color {accent};
@define-color selected_fg_color {accent_fg};
@define-color theme_unfocused_bg_color {bg};
@define-color theme_unfocused_fg_color {text};
@define-color theme_unfocused_base_color {large};
@define-color theme_unfocused_text_color {text};
@define-color theme_unfocused_selected_bg_color {surface2};
@define-color theme_unfocused_selected_fg_color {text};
@define-color insensitive_bg_color {surface};
@define-color insensitive_fg_color {text};
@define-color borders {border};

window,
window.background,
.background {{
  background-color: @theme_bg_color;
  color: @theme_fg_color;
}}

/* Headerbars are client-side GTK widgets. Do not style the generic
 * .titlebar class: classic server-side decorations are owned by Mutter and
 * setting only their foreground can produce white text on a light frame.
 */
headerbar,
headerbar.titlebar {{
  background-color: {surface};
  color: {text};
  border-color: {border};
}}

/* GTK3 client-side decorated windows, e.g. virt-manager. */
window.csd .titlebar,
window.solid-csd .titlebar {{
  background-image: none;
  background-color: {surface};
  color: {text};
  border-color: {border};
  text-shadow: none;
}}

window.csd .titlebar:backdrop,
window.solid-csd .titlebar:backdrop {{
  background-image: none;
  background-color: {large};
  color: {text};
  border-color: {border};
  text-shadow: none;
}}

/* Keep CSD window controls visually lighter than normal app buttons. */
window.csd .titlebar button,
window.solid-csd .titlebar button {{
  background-image: none;
  background-color: transparent;
  color: {text};
  border-color: transparent;
}}

window.csd .titlebar button:hover,
window.solid-csd .titlebar button:hover {{
  background-color: {surface2};
  color: {text};
}}

window.csd .titlebar button:active,
window.csd .titlebar button:checked,
window.solid-csd .titlebar button:active,
window.solid-csd .titlebar button:checked {{
  background-color: {accent};
  color: {accent_fg};
}}

menubar {{
  background-color: {panel};
  color: {text};
  border-color: {border};
}}
menubar > menuitem {{
  background-color: transparent;
  color: {text};
}}
menubar > menuitem:hover,
menubar > menuitem:checked {{
  background-color: {surface2};
  color: {text};
}}

toolbar,
.toolbar,
actionbar {{
  background-color: {surface};
  color: {text};
  border-color: {border};
}}
toolbar separator,
.toolbar separator,
separator {{
  background-color: {border};
}}

.view,
treeview.view,
iconview,
textview text,
list,
listbox,
flowbox {{
  background-color: {large};
  color: {text};
}}

treeview.view header button {{
  background-color: {surface};
  color: {text};
  border-color: {border};
  border-radius: 0;
}}
treeview.view header button:hover {{
  background-color: {surface2};
}}

*:selected,
row:selected,
treeview.view:selected,
iconview:selected {{
  background-color: {accent};
  color: {accent_fg};
}}
*:selected:backdrop,
row:selected:backdrop,
treeview.view:selected:backdrop,
iconview:selected:backdrop {{
  background-color: {surface2};
  color: {text};
}}

button {{
  background-image: none;
  background-color: {surface2};
  color: {text};
  border: 1px solid {border};
  border-radius: 8px;
}}
button:hover {{
  background-image: none;
  background-color: {card};
}}
button:active,
button:checked {{
  background-image: none;
  background-color: {accent};
  color: {accent_fg};
}}

entry,
spinbutton,
combobox button {{
  background-color: {large};
  color: {text};
  border-color: {border};
}}
entry selection {{
  background-color: {accent};
  color: {accent_fg};
}}

menu,
.menu,
.context-menu,
popover {{
  background-color: {surface};
  color: {text};
  border-color: {border};
}}
menuitem {{
  color: {text};
}}
menuitem:hover {{
  background-color: {accent};
  color: {accent_fg};
}}

notebook > header {{
  background-color: {surface};
  color: {text};
  border-color: {border};
}}

/* GTK3 notebook content, e.g. virt-manager hardware/details view. */
notebook > stack {{
  background-color: {large};
  color: {text};
}}

viewport {{
  background-color: {large};
  color: {text};
}}

notebook > header > tabs > tab {{
  color: {text};
}}
notebook > header > tabs > tab:checked {{
  background-color: {surface2};
  color: {text};
}}

/* GTK3 notebook tabs, e.g. virt-manager preferences */
notebook > header,
notebook > header.top,
notebook > header.bottom,
notebook > header.left,
notebook > header.right {{
  background-color: {panel};
  color: {text};
  border-color: {border};
}}

notebook > header > tabs > tab {{
  background-color: {surface};
  color: {text};
  border-color: {border};
  box-shadow: none;
}}

notebook > header > tabs > tab:hover {{
  background-color: {accent};
  color: {accent_fg};
  border-color: {accent};
}}

notebook > header > tabs > tab:checked {{
  background-color: {accent};
  color: {accent_fg};
  border-color: {accent};
}}

notebook > header > tabs > tab:backdrop {{
  background-color: {large};
  color: {text};
  border-color: {border};
}}

notebook > header > tabs > tab:disabled,
notebook > header > tabs > tab:disabled:hover {{
  background-color: {large};
  color: {border};
  border-color: {border};
  box-shadow: none;
}}

.sidebar,
.navigation-sidebar {{
  background-color: {card};
  color: {text};
}}
.sidebar row:selected,
.navigation-sidebar row:selected {{
  background-color: {accent};
  color: {accent_fg};
}}

frame,
scrolledwindow {{
  border-color: {border};
}}
tooltip {{
  background-color: {surface2};
  color: {text};
  border-color: {border};
}}

/* Scrollbars */
scrollbar trough {{
  background-color: {large};
}}

scrollbar slider {{
  background-color: {border};
  border-radius: 999px;
}}

scrollbar slider:hover {{
  background-color: {surface2};
}}

/* Sliders */
scale trough {{
  background-color: {surface};
}}

scale highlight {{
  background-color: {accent};
}}

scale slider {{
  background-color: {text};
  border-color: {border};
}}

/* Progress bars */
progressbar trough {{
  background-color: {surface};
}}

progressbar progress {{
  background-color: {accent};
}}

/* Switches */
switch {{
  background-image: none;
  background-color: {surface};
  border-color: {border};
}}

switch:checked {{
  background-color: {accent};
}}

switch slider {{
  background-image: none;
  background-color: {text};
}}

/* Check / radio indicators */
checkbutton check,
radiobutton radio {{
  background-image: none;
  background-color: {large};
  border-color: {border};
}}

checkbutton:checked check,
radiobutton:checked radio {{
  background-color: {accent};
  color: {accent_fg};
}}

/* GtkPaned splitters */
paned > separator {{
  background-color: {border};
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
