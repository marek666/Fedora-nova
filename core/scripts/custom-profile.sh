#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

case "${1:-list}" in
  list)
    python3 "$SCRIPT_DIR/profile-info.py" list \
      "$NOVA_APP_DIR/config/profiles.json" "$NOVA_CUSTOM_DIR" |
      awk -F '\t' '$4=="custom" {printf "%-28s %s — %s\n", $1, $2, $3}'
    ;;
  delete)
    [[ -n "${2:-}" ]] || die "Chybí ID vlastního profilu."
    deleted="$("$SCRIPT_DIR/forge-profile.py" delete "$2")"
    log "Odstraněn profil: $deleted"
    ;;
  *)
    die "Použij: custom-profile.sh {list|delete PROFILE}"
    ;;
esac
