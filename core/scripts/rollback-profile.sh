#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

PREVIOUS="$(cat "$NOVA_CONFIG_DIR/previous-profile" 2>/dev/null || true)"
[[ -n "$PREVIOUS" ]] || die "Předchozí profil není uložený."
CURRENT="$(current_profile)"
printf '%s\n' "$CURRENT" > "$NOVA_CONFIG_DIR/previous-profile"

log "Vracíme profil $CURRENT → $PREVIOUS"
NOVA_SKIP_HISTORY=1 "$SCRIPT_DIR/apply-profile.sh" "$PREVIOUS" --reload

if [[ -s "$NOVA_CONFIG_DIR/previous-dock" ]]; then
  DOCK="$(cat "$NOVA_CONFIG_DIR/previous-dock")"
  CURRENT_DOCK="$(cat "$NOVA_CONFIG_DIR/current-dock" 2>/dev/null || echo profile-default)"
  printf '%s\n' "$CURRENT_DOCK" > "$NOVA_CONFIG_DIR/previous-dock"
  [[ "$DOCK" != "profile-default" ]] && "$SCRIPT_DIR/apply-dock.sh" "$DOCK" || true
fi
if [[ -s "$NOVA_CONFIG_DIR/previous-motion" ]]; then
  MOTION="$(cat "$NOVA_CONFIG_DIR/previous-motion")"
  CURRENT_MOTION="$(cat "$NOVA_CONFIG_DIR/current-motion" 2>/dev/null || echo balanced)"
  printf '%s\n' "$CURRENT_MOTION" > "$NOVA_CONFIG_DIR/previous-motion"
  "$SCRIPT_DIR/apply-motion.sh" "$MOTION" || true
fi
