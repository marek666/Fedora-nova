#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

printf 'Fedora Nova compatibility report\n'
printf '================================\n'

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  printf 'OS:             %s %s\n' "${NAME:-unknown}" "${VERSION_ID:-unknown}"
else
  printf 'OS:             unknown\n'
fi

printf 'Session:        %s\n' "${XDG_CURRENT_DESKTOP:-unknown}"
printf 'Session type:   %s\n' "${XDG_SESSION_TYPE:-unknown}"
printf 'GNOME Shell:    %s\n' "$(gnome-shell --version 2>/dev/null || echo unavailable)"
printf 'gsettings:      %s\n' "$(command -v gsettings || echo unavailable)"
printf 'dconf:          %s\n' "$(command -v dconf || echo unavailable)"
printf 'mutter-devkit:  %s\n' "$([[ -x /usr/libexec/mutter-devkit ]] && echo /usr/libexec/mutter-devkit || echo unavailable)"
printf 'Ptyxis:         %s\n' "$(ptyxis --version 2>/dev/null || echo unavailable)"

profile_file="${XDG_CONFIG_HOME:-$HOME/.config}/fedora-nova/current-profile"
printf 'Nova profile:   %s\n' "$(cat "$profile_file" 2>/dev/null || echo not-set)"
printf '\nRequired extensions visible to current Shell:\n'
for uuid in \
  user-theme@gnome-shell-extensions.gcampax.github.com \
  dash-to-dock@micxgx.gmail.com \
  topbar-all-monitors@fa8i.github.io; do
  if gnome-extensions info "$uuid" >/dev/null 2>&1; then
    printf '  OK      %s\n' "$uuid"
  else
    printf '  MISSING %s\n' "$uuid"
  fi
done

printf '\nPerformance safety:\n'
if gnome-extensions info blur-my-shell@aunetx >/dev/null 2>&1; then
  if gnome-extensions list --enabled 2>/dev/null | grep -Fxq blur-my-shell@aunetx; then
    printf '  WARN    Blur My Shell je zapnutý; Fedora Nova doporučuje vypnout.\n'
  else
    printf '  OK      Blur My Shell je nainstalovaný, ale vypnutý.\n'
  fi
else
  printf '  OK      Blur My Shell není nainstalovaný.\n'
fi
