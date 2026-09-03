#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

"$SCRIPT_DIR/status.sh"
printf '\nKontroly:\n'
issues=0

for uuid in user-theme@gnome-shell-extensions.gcampax.github.com \
            dash-to-dock@micxgx.gmail.com; do
  if gnome-extensions info "$uuid" >/dev/null 2>&1; then
    printf '  OK   %s je dostupné\n' "$uuid"
  else
    printf '  FAIL %s chybí\n' "$uuid"
    issues=$((issues+1))
  fi
done

if [[ -d "$NOVA_DATA_HOME/gnome-shell/extensions/topbar-all-monitors@fa8i.github.io" ]]; then
  printf '  OK   Top Bar All Monitors je nainstalovaný.\n'
else
  printf '  WARN Top Bar All Monitors není nainstalovaný.\n'
  issues=$((issues+1))
fi
if gnome-extensions list --enabled 2>/dev/null | grep -Fxq topbar-all-monitors@fa8i.github.io ||
   gsettings get org.gnome.shell enabled-extensions 2>/dev/null | grep -Fq topbar-all-monitors@fa8i.github.io; then
  printf '  OK   Panel na sekundárních monitorech je povolený.\n'
else
  printf '  WARN Panel na sekundárních monitorech není povolený.\n'
  issues=$((issues+1))
fi

if gsettings get org.gnome.desktop.interface icon-theme 2>/dev/null | grep -Fq 'Tela-circle'; then
  printf '  OK   Tela Circle je aktivní.\n'
elif gsettings get org.gnome.desktop.interface icon-theme 2>/dev/null | grep -Fq 'Fedora-Nova-Steam'; then
  printf '  OK   Fedora Nova Steam icon theme je aktivní.\n'
else
  printf '  INFO Aktivní icon theme není Tela Circle.\n'
fi

if [[ -f "$NOVA_SESSION_AUTOSTART" ]]; then
  printf '  OK   Fedora Nova session restore je zapnutý.\n'
else
  printf '  WARN Fedora Nova session restore není zapnutý.\n'
  issues=$((issues+1))
fi
if [[ -f "$NOVA_CONFIG_HOME/gnome-initial-setup-done" &&
      -f "$NOVA_AUTOSTART_DIR/org.gnome.Tour.desktop" ]]; then
  printf '  OK   GNOME/Fedora welcome dialog je vypnutý.\n'
else
  printf '  WARN GNOME/Fedora welcome dialog nemusí být vypnutý.\n'
  issues=$((issues+1))
fi

if gnome-extensions list --enabled 2>/dev/null |
    grep -Fxq blur-my-shell@aunetx; then
  printf '  WARN Blur My Shell je zapnutý — může vrátit lag compositoru.\n'
  issues=$((issues+1))
else
  printf '  OK   Blur My Shell není aktivní.\n'
fi

profile="$(current_profile)"
if info="$(
  python3 "$SCRIPT_DIR/profile-info.py" shell "$profile" \
    "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" 2>/dev/null
)"; then
  eval "$info"
  css="$NOVA_THEMES_DIR/$THEME/gnome-shell/gnome-shell.css"
  wallpaper="$NOVA_WALLPAPER_DIR/$WALL"
else
  css=""
  wallpaper=""
  printf '  FAIL Profil nelze načíst: %s\n' "$profile"
  issues=$((issues+1))
fi

if [[ -n "$css" && -f "$css" ]]; then
  printf '  OK   Theme soubor existuje.\n'
  if grep -Fq '/* NOVA_CURVE_START */' "$css"; then
    printf '  OK   Continuous Curve vrstva je přítomná.\n'
  else
    printf '  WARN Continuous Curve vrstva chybí.\n'
    issues=$((issues+1))
  fi
  if grep -Fq '/* NOVA_HOVER_START */' "$css"; then
    printf '  OK   Nova hover vrstva je přítomná.\n'
  else
    printf '  WARN Nova hover vrstva chybí.\n'
    issues=$((issues+1))
  fi
else
  printf '  FAIL Theme soubor chybí.\n'
  issues=$((issues+1))
fi

if [[ -n "$css" ]] &&
   grep -Eqi 'blur-effect|filter:[[:space:]]*blur' "$css" 2>/dev/null; then
  printf '  WARN Theme obsahuje blur CSS.\n'
  issues=$((issues+1))
else
  printf '  OK   Aktivní theme neobsahuje CSS blur.\n'
fi

if [[ -n "$css" ]] && python3 - "$css" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
blocks = re.findall(r"\.quick-settings\s*\{([^}]*)\}", text, re.S)
raise SystemExit(0 if any(re.search(r"box-shadow\s*:\s*(?!none)", b) for b in blocks) else 1)
PY
then
  printf '  WARN Quick Settings mohou obsahovat drahý stín.\n'
  issues=$((issues+1))
else
  printf '  OK   Quick Settings nemají zjevný drahý stín.\n'
fi

if [[ -n "$wallpaper" && -f "$wallpaper" ]]; then
  printf '  OK   Wallpaper profilu existuje.\n'
else
  printf '  FAIL Wallpaper profilu chybí.\n'
  issues=$((issues+1))
fi

printf '\nPoslední GNOME Shell / Mutter chyby v tomto bootu:\n'
journalctl --user -b --no-pager 2>/dev/null |
  grep -Ei 'gnome-shell|mutter|st-theme|extension.*error' |
  tail -n 25 || true

printf '\nVýsledek: %s problémů/varování.\n' "$issues"
