#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

profile="$(current_profile)"
profile_title="$profile"
profile_kind="unknown"
if info="$(
  python3 "$SCRIPT_DIR/profile-info.py" shell "$profile" \
    "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" 2>/dev/null
)"; then
  eval "$info"
  profile_title="$TITLE"
  profile_kind="$PROFILE_KIND"
fi

latest_snapshot="$(
  find "$NOVA_STATE_DIR/snapshots" -mindepth 1 -maxdepth 1 \
    -type d -printf '%f\n' 2>/dev/null | sort | tail -n 1
)"
custom_count="$(
  find "$NOVA_CUSTOM_DIR" -maxdepth 1 -type f -name 'custom-*.json' \
    2>/dev/null | wc -l
)"

printf 'Fedora Nova %s\n' "$NOVA_VERSION"
printf '=================\n'
printf 'Profil:            %s (%s, %s)\n' "$profile" "$profile_title" "$profile_kind"
printf 'Předchozí:         %s\n' "$(cat "$NOVA_CONFIG_DIR/previous-profile" 2>/dev/null || echo —)"
printf 'Forge profily:     %s\n' "$custom_count"
printf 'Dock preset:       %s\n' "$(cat "$NOVA_CONFIG_DIR/current-dock" 2>/dev/null || echo profile-default)"
printf 'Pohyb:             %s\n' "$(cat "$NOVA_CONFIG_DIR/current-motion" 2>/dev/null || echo balanced)"
printf 'Křivky:            %s\n' "$(current_curve)"
printf 'Hover:             %s\n' "$(current_hover)"
printf 'GTK aplikace:      %s\n' "$(current_gtk)"
printf 'Ikony preset:      %s\n' "$(current_icons)"
printf 'Session restore:   %s\n' "$([[ -f "$NOVA_SESSION_AUTOSTART" ]] && echo zapnuto || echo vypnuto)"
printf 'Poslední snapshot: %s\n' "${latest_snapshot:-—}"
printf 'Shell theme:       %s\n' "$(gsettings get org.gnome.shell.extensions.user-theme name 2>/dev/null || echo unavailable)"
printf 'Icon theme:        %s\n' "$(gsettings get org.gnome.desktop.interface icon-theme 2>/dev/null || echo unavailable)"
printf 'Accent:            %s\n' "$(gsettings get org.gnome.desktop.interface accent-color 2>/dev/null || echo unavailable)"
printf 'GNOME Shell:       %s\n' "$(gnome-shell --version 2>/dev/null || echo unavailable)"
printf 'Session:           %s / %s\n' "${XDG_CURRENT_DESKTOP:-unknown}" "${XDG_SESSION_TYPE:-unknown}"

printf '\nExtensions:\n'
for uuid in user-theme@gnome-shell-extensions.gcampax.github.com \
            dash-to-dock@micxgx.gmail.com topbar-all-monitors@fa8i.github.io \
            blur-my-shell@aunetx; do
  if gnome-extensions info "$uuid" >/dev/null 2>&1; then
    if gnome-extensions list --enabled 2>/dev/null | grep -Fxq "$uuid"; then
      state=ENABLED
    else
      state=disabled
    fi
    printf '  %-9s %s\n' "$state" "$uuid"
  else
    printf '  %-9s %s\n' missing "$uuid"
  fi
done
