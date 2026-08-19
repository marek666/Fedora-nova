#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

PROFILE="${1:-tech}"
RELOAD=0
[[ "${2:-}" == "--reload" ]] && RELOAD=1

if [[ "$PROFILE" == "list" ]]; then
  python3 "$SCRIPT_DIR/profile-info.py" list \
    "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" |
    awk -F '\t' '{printf "%-28s %-20s %s%s\n", $1, $2, $3, ($4=="custom" ? " [Forge]" : "")}'
  exit 0
fi

ensure_gnome_session
command_exists python3 || die "Chybí python3."

PROFILE_VARS="$(
  python3 "$SCRIPT_DIR/profile-info.py" shell "$PROFILE" \
    "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR"
)" || die "Profil se nepodařilo načíst: $PROFILE"
eval "$PROFILE_VARS"

THEME_HOME="$NOVA_THEMES_DIR/$THEME/gnome-shell/gnome-shell.css"
[[ -f "$THEME_HOME" ]] || die "Theme $THEME není nainstalované."
if ! grep -Fq '/* NOVA_CURVE_START */' "$THEME_HOME"; then
  "$SCRIPT_DIR/apply-curve.sh" "$(current_curve)" --no-reload >/dev/null
fi
if ! grep -Fq '/* NOVA_HOVER_START */' "$THEME_HOME"; then
  "$SCRIPT_DIR/apply-hover.sh" "$(current_hover)" >/dev/null
fi

mkdir -p "$NOVA_CONFIG_DIR"
OLD_PROFILE="$(current_profile)"
if [[ "${NOVA_SKIP_HISTORY:-0}" != 1 && "$OLD_PROFILE" != "$PROFILE" ]]; then
  printf '%s\n' "$OLD_PROFILE" > "$NOVA_CONFIG_DIR/previous-profile"
  [[ -f "$NOVA_CONFIG_DIR/current-dock" ]] &&
    cp "$NOVA_CONFIG_DIR/current-dock" "$NOVA_CONFIG_DIR/previous-dock" || true
  [[ -f "$NOVA_CONFIG_DIR/current-motion" ]] &&
    cp "$NOVA_CONFIG_DIR/current-motion" "$NOVA_CONFIG_DIR/previous-motion" || true
fi

log "Vypínám problematický dynamický blur"
disable_extension blur-my-shell@aunetx

log "Aktivuji profil $PROFILE — $TITLE"
enable_extension user-theme@gnome-shell-extensions.gcampax.github.com
enable_extension dash-to-dock@micxgx.gmail.com
try_set org.gnome.shell.extensions.user-theme name "'$THEME'"
try_set org.gnome.desktop.interface accent-color "'$ACCENT_NAME'"

WALLPAPER="$NOVA_WALLPAPER_DIR/$WALL"
[[ -f "$WALLPAPER" ]] || die "Wallpaper profilu chybí: $WALLPAPER"
WALLPAPER_URI="file://$WALLPAPER"
try_set org.gnome.desktop.background picture-uri "'$WALLPAPER_URI'"
try_set org.gnome.desktop.background picture-uri-dark "'$WALLPAPER_URI'"
try_set org.gnome.desktop.background picture-options "'zoom'"

try_set org.gnome.desktop.screensaver picture-uri "'$WALLPAPER_URI'"
try_set org.gnome.desktop.screensaver picture-options "'zoom'"

log "Nastavuji dock pro profil $PROFILE"
SCHEMA=org.gnome.shell.extensions.dash-to-dock
try_set "$SCHEMA" dock-position "'BOTTOM'"
try_set "$SCHEMA" extend-height false
try_set "$SCHEMA" always-center-icons false
try_set "$SCHEMA" autohide true
try_set "$SCHEMA" intellihide true
try_set "$SCHEMA" intellihide-mode "'FOCUS_APPLICATION_WINDOWS'"
try_set "$SCHEMA" autohide-in-fullscreen true
try_set "$SCHEMA" require-pressure-to-show false
try_set "$SCHEMA" dash-max-icon-size "$ICON_SIZE"
try_set "$SCHEMA" icon-size-fixed false
try_set "$SCHEMA" show-trash false
try_set "$SCHEMA" show-mounts false
try_set "$SCHEMA" show-favorites true
try_set "$SCHEMA" show-running true
try_set "$SCHEMA" show-show-apps-button true
try_set "$SCHEMA" show-apps-at-top false
try_set "$SCHEMA" custom-theme-shrink true
try_set "$SCHEMA" apply-custom-theme false
try_set "$SCHEMA" custom-background-color true
try_set "$SCHEMA" background-color "'$DOCK_COLOR'"
try_set "$SCHEMA" transparency-mode "'FIXED'"
try_set "$SCHEMA" background-opacity "$OPACITY"
try_set "$SCHEMA" running-indicator-style "'$INDICATOR'"
try_set "$SCHEMA" running-indicator-dominant-color false
try_set "$SCHEMA" custom-theme-customize-running-dots true
try_set "$SCHEMA" custom-theme-running-dots-color "'$DOT_COLOR'"
try_set "$SCHEMA" custom-theme-running-dots-border-color "'$DOT_BORDER'"
try_set "$SCHEMA" custom-theme-running-dots-border-width 1
try_set "$SCHEMA" click-action "'minimize-or-previews'"
try_set "$SCHEMA" scroll-action "'cycle-windows'"

printf '%s\n' "$PROFILE" > "$NOVA_CONFIG_DIR/current-profile"

MOTION="$(cat "$NOVA_CONFIG_DIR/current-motion" 2>/dev/null || echo balanced)"
"$SCRIPT_DIR/apply-motion.sh" "$MOTION"

if [[ "$(current_gtk)" == "on" ]]; then
  "$SCRIPT_DIR/gtk-theme.sh" refresh >/dev/null || true
fi

if [[ $RELOAD -eq 1 ]]; then
  "$SCRIPT_DIR/reload-theme.sh" || true
fi

log "Profil $PROFILE je nastavený. Pokud se vše nepřekreslí, proveď relogin."
