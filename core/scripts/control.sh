#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
PY
then
  exec python3 "$SCRIPT_DIR/settings.py" "$@"
fi
printf 'WARN: GTK4/libadwaita Python bindings nejsou dostupné; spouštím Zenity fallback.\n' >&2
exec "$SCRIPT_DIR/control-zenity.sh" "$@"
