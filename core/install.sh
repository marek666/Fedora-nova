#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_DIR/scripts/lib.sh"

DRY_RUN=0
SKIP_PACKAGES=0
NO_APPLY=0
FORCE_NON_FEDORA=0
PROFILE=""

usage() {
  cat <<'USAGE'
Fedora Nova installer

Usage: ./install.sh [options]

  --profile NAME     vestavěný nebo dříve vytvořený Forge profil
                     bez volby zachová aktivní profil při upgradu
  --dry-run          pouze vypíše plánované kroky
  --skip-packages    neinstaluje RPM balíčky
  --no-apply         nainstaluje soubory, ale nezmění GNOME nastavení
  --force-non-fedora dovolí běh mimo Fedoru (bez záruky)
  -h, --help         nápověda
USAGE
}

while (($#)); do
  case "$1" in
    --profile) shift; (($#)) || die "Za --profile chybí hodnota."; PROFILE="$1" ;;
    --dry-run) DRY_RUN=1 ;;
    --skip-packages) SKIP_PACKAGES=1 ;;
    --no-apply) NO_APPLY=1 ;;
    --force-non-fedora) FORCE_NON_FEDORA=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Neznámá volba: $1" ;;
  esac
  shift
done

if [[ -z "$PROFILE" ]]; then
  PROFILE="$(current_profile)"
fi
if ! python3 "$PROJECT_DIR/scripts/profile-info.py" shell "$PROFILE" \
      "$PROJECT_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" >/dev/null 2>&1; then
  die "Neznámý profil '$PROFILE'."
fi
[[ $EUID -ne 0 ]] || die "Nespouštěj celý instalátor jako root."

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "fedora" && $FORCE_NON_FEDORA -ne 1 ]]; then
    die "Tato verze je určená pro Fedoru. Pro test použij --force-non-fedora."
  fi
fi

run() {
  if [[ $DRY_RUN -eq 1 ]]; then printf '+ '; printf '%q ' "$@"; printf '\n'; else "$@"; fi
}

log "Instaluji $NOVA_NAME $NOVA_VERSION (profil: $PROFILE)"

if [[ $SKIP_PACKAGES -ne 1 ]]; then
  command_exists dnf || die "Chybí dnf."
  mapfile -t PACKAGES < <(grep -Ev '^[[:space:]]*(#|$)' "$PROJECT_DIR/config/packages.txt")
  log "Instaluji oficiální Fedora balíčky"
  run sudo dnf install -y "${PACKAGES[@]}"
fi

if [[ $DRY_RUN -ne 1 && $NO_APPLY -ne 1 ]]; then
  "$PROJECT_DIR/scripts/backup-settings.sh" >/dev/null
fi

APP_DEST="${XDG_DATA_HOME:-$HOME/.local/share}/fedora-nova"
log "Instaluji trvalou kopii do $APP_DEST"
if [[ "$PROJECT_DIR" == "$APP_DEST" ]]; then
  log "Instalátor už běží z trvalé kopie; kopírování přeskakuji"
elif [[ $DRY_RUN -eq 1 ]]; then
  printf '+ rm -rf %q\n' "$APP_DEST"
  printf '+ mkdir -p %q\n' "$APP_DEST"
  printf '+ cp -a %q/. %q/\n' "$PROJECT_DIR" "$APP_DEST"
else
  rm -rf "$APP_DEST"
  mkdir -p "$APP_DEST"
  cp -a "$PROJECT_DIR/." "$APP_DEST/"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  printf '+ %q\n' "$APP_DEST/scripts/install-assets.sh"
else
  "$APP_DEST/scripts/install-assets.sh"
fi

if [[ $NO_APPLY -ne 1 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '+ %q full %q --skip-assets --no-backup\n' "$APP_DEST/scripts/apply-preset.sh" "$PROFILE"
  else
    "$APP_DEST/scripts/apply-preset.sh" full "$PROFILE" --skip-assets --no-backup
  fi
fi

cat <<EOF2

Fedora Nova $NOVA_VERSION — Hover & App Integration byla nainstalována.

Aktivní profil: $PROFILE
Nastavení:      fedora-nova settings
Terminál:       fedora-nova status
Full setup:     fedora-nova preset full --reload
Hover:          fedora-nova hover circle --reload
GTK aplikace:   fedora-nova gtk status
Ikony:          fedora-nova icons tela-steam
Steam ikony:    fedora-nova steam-icons round
Monitory:       fedora-nova monitors status
Křivky:        fedora-nova curve squircle --reload
Forge:          fedora-nova forge Ultraviolet '#D630F2' '#2ED8E8'
Přepnutí:       fedora-nova profile pulse --reload
Rollback:        fedora-nova rollback
Snapshot:        fedora-nova snapshot create pred-zmenou
Náhled:         fedora-nova preview
Diagnostika:    fedora-nova doctor
Nouzový režim:  fedora-nova safe-mode

Pokud shell neukáže všechny změny, odhlas se a znovu přihlas.
EOF2
