#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

usage() {
  cat <<'USAGE'
Usage:
  forge-profile.sh NAME PRIMARY [SECONDARY] [--no-apply]

Examples:
  forge-profile.sh Ultraviolet '#D630F2' '#2ED8E8'
  forge-profile.sh Ember '#FF5C7A'
USAGE
}

(($# >= 2)) || { usage; exit 2; }

NAME="$1"
PRIMARY="$2"
shift 2
SECONDARY=""
NO_APPLY=0

while (($#)); do
  case "$1" in
    --no-apply) NO_APPLY=1 ;;
    --*) die "Neznámá volba: $1" ;;
    *) [[ -z "$SECONDARY" ]] || die "Bylo zadáno příliš mnoho barev."; SECONDARY="$1" ;;
  esac
  shift
done

command_exists python3 || die "Chybí python3."
mkdir -p "$NOVA_CUSTOM_DIR"

if [[ -n "$SECONDARY" ]]; then
  PROFILE_ID="$("$SCRIPT_DIR/forge-profile.py" create "$NAME" "$PRIMARY" "$SECONDARY")"
else
  PROFILE_ID="$("$SCRIPT_DIR/forge-profile.py" create "$NAME" "$PRIMARY")"
fi

"$SCRIPT_DIR/apply-curve.sh" "$(current_curve)" --no-reload >/dev/null
"$SCRIPT_DIR/apply-hover.sh" "$(current_hover)" >/dev/null
log "Vytvořen profil: $PROFILE_ID"
if [[ $NO_APPLY -eq 0 ]]; then
  "$SCRIPT_DIR/apply-profile.sh" "$PROFILE_ID" --reload
fi
printf '%s\n' "$PROFILE_ID"
