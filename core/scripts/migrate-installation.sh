#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

DRY_RUN=0
case "${1:-}" in
  "") ;;
  --dry-run) DRY_RUN=1 ;;
  -h|--help)
    cat <<'USAGE'
Usage: fedora-nova migrate-installation [--dry-run]

Safely migrates Fedora Nova user integration from the legacy standalone
layout to the currently installed canonical package runtime.
USAGE
    exit 0
    ;;
  *) die "Použij: fedora-nova migrate-installation [--dry-run]" ;;
esac

physical_core="$(realpath -e -- "$SCRIPT_DIR/..")" || die "Nelze určit fyzický core runtime."
case "$physical_core" in
  */share/fedora-nova/core) ;;
  *) die "Migrace je dostupná pouze z canonical package instalace Fedora Nova." ;;
esac
package_root="${physical_core%/core}"
package_layout_present "$package_root" || die "Aktuální runtime není kompletní canonical package instalace."
prefix="${physical_core%/share/fedora-nova/core}"
[[ -n "$prefix" && "$prefix" == /* && "$prefix" != / ]] || die "Nelze určit bezpečný package prefix."
canonical_cli="$prefix/bin/fedora-nova"
canonical_settings="$prefix/bin/fedora-nova-settings"
[[ -f "$canonical_cli" && -x "$canonical_cli" ]] || die "Chybí canonical Fedora Nova CLI: $canonical_cli"
[[ -f "$canonical_settings" && -x "$canonical_settings" ]] || die "Chybí production Settings launcher: $canonical_settings"

legacy_wrapper="$HOME/.local/bin/fedora-nova"
legacy_desktop="$NOVA_DATA_HOME/applications/fedora-nova-control.desktop"
session_launcher="$NOVA_CONFIG_DIR/session-restore"
session_desktop="$NOVA_SESSION_AUTOSTART"
marker="$NOVA_STATE_DIR/migration-canonical-layout"
backup_dir=""

same_file() {
  [[ -e "$1" && -e "$2" ]] || return 1
  [[ "$(realpath -e -- "$1")" == "$(realpath -e -- "$2")" ]]
}

managed_legacy_wrapper() {
  local first second third
  [[ -f "$1" ]] || return 1
  IFS= read -r first < "$1" || true
  second="$(sed -n '2p' -- "$1")"
  third="$(sed -n '3p' -- "$1")"
  [[ "$first" == '#!/usr/bin/env bash' ]] || return 1
  [[ "$second" == 'exec "'*'/nova" "$@"' ]] || return 1
  [[ -z "$third" ]]
}

managed_legacy_desktop() {
  [[ -f "$1" ]] || return 1
  grep -Fxq 'Type=Application' "$1" &&
    grep -Fxq 'Icon=fedora-nova' "$1" &&
    grep -Eq '^Exec=fedora-nova (settings|control)$' "$1"
}

managed_session_launcher() {
  [[ -f "$1" ]] || return 1
  grep -Fxq '#!/usr/bin/env bash' "$1" &&
    grep -Fq 'session-restore --quiet' "$1"
}

managed_session_desktop() {
  [[ -f "$1" ]] || return 1
  grep -Fxq 'Type=Application' "$1" &&
    grep -Fxq 'Name=Fedora Nova Session Restore' "$1" &&
    grep -q '^Exec=' "$1"
}

# Preflight every file before mutating anything.
if [[ -e "$legacy_wrapper" ]] && ! same_file "$legacy_wrapper" "$canonical_cli"; then
  managed_legacy_wrapper "$legacy_wrapper" ||
    die "Nelze bezpečně migrovat: $legacy_wrapper není rozpoznaný Fedora Nova legacy wrapper."
fi
if [[ -e "$legacy_desktop" ]]; then
  managed_legacy_desktop "$legacy_desktop" ||
    die "Nelze bezpečně migrovat: $legacy_desktop není rozpoznaná legacy Fedora Nova desktop položka."
fi
if [[ -e "$session_launcher" ]]; then
  managed_session_launcher "$session_launcher" ||
    die "Nelze bezpečně migrovat: $session_launcher není rozpoznaný Fedora Nova session launcher."
fi
if [[ -e "$session_desktop" ]]; then
  managed_session_desktop "$session_desktop" ||
    die "Nelze bezpečně migrovat: $session_desktop není rozpoznaná Fedora Nova session desktop položka."
fi

ensure_backup_dir() {
  [[ -n "$backup_dir" ]] && return 0
  mkdir -p "$NOVA_STATE_DIR/migrations"
  backup_dir="$(mktemp -d "$NOVA_STATE_DIR/migrations/legacy-to-canonical.XXXXXX")"
}

backup_file() {
  local source="$1" name="$2"
  [[ -e "$source" ]] || return 0
  if [[ $DRY_RUN -eq 1 ]]; then
    printf 'DRY-RUN backup %s\n' "$source"
    return 0
  fi
  ensure_backup_dir
  cp -a -- "$source" "$backup_dir/$name"
}

remove_managed() {
  local path="$1"
  [[ -e "$path" ]] || return 0
  if [[ $DRY_RUN -eq 1 ]]; then
    printf 'DRY-RUN remove %s\n' "$path"
  else
    rm -f -- "$path"
  fi
}

session_was_enabled=0
[[ -e "$session_desktop" ]] && session_was_enabled=1

if [[ -e "$legacy_wrapper" ]] && ! same_file "$legacy_wrapper" "$canonical_cli"; then
  backup_file "$legacy_wrapper" fedora-nova-wrapper
  remove_managed "$legacy_wrapper"
fi

if [[ -e "$legacy_desktop" ]]; then
  backup_file "$legacy_desktop" fedora-nova-control.desktop
  remove_managed "$legacy_desktop"
fi

if [[ -e "$session_launcher" ]]; then
  backup_file "$session_launcher" session-restore
fi
if [[ -e "$session_desktop" ]]; then
  backup_file "$session_desktop" fedora-nova-session.desktop
fi

if [[ $session_was_enabled -eq 1 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    printf 'DRY-RUN regenerate session restore with %s\n' "$canonical_cli"
  else
    "$SCRIPT_DIR/session-restore.sh" enable
  fi
elif [[ -e "$session_launcher" ]]; then
  # Preserve disabled state while removing a stale orphan launcher.
  remove_managed "$session_launcher"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  printf 'DRY-RUN write migration marker %s\n' "$marker"
  exit 0
fi

mkdir -p "$NOVA_STATE_DIR"
marker_tmp="$(mktemp "$NOVA_STATE_DIR/.migration-canonical-layout.XXXXXX")"
trap 'rm -f -- "$marker_tmp"' EXIT
{
  printf 'version=1\n'
  printf 'canonical_prefix=%s\n' "$prefix"
  printf 'canonical_cli=%s\n' "$canonical_cli"
  printf 'backup_dir=%s\n' "$backup_dir"
  printf 'session_enabled=%s\n' "$session_was_enabled"
  printf 'migrated_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$marker_tmp"
mv -f -- "$marker_tmp" "$marker"
trap - EXIT

log "Legacy integrace byla bezpečně přepnuta na canonical Fedora Nova runtime."
[[ -n "$backup_dir" ]] && log "Záloha migrovaných souborů: $backup_dir"
