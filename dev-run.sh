#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

MODE="${1:-host}"
case "$MODE" in
  host)
    export FEDORA_NOVA_PREVIEW=0
    ;;
  preview)
    export FEDORA_NOVA_PREVIEW=1
    ;;
  *)
    echo "Použij: ./dev-run.sh [host|preview]" >&2
    exit 2
    ;;
esac

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export FEDORA_NOVA_PROJECT_ROOT="$ROOT"
export FEDORA_NOVA_CORE="$ROOT/core"

SCHEMA_DIR="$ROOT/.dev-build/schemas"
mkdir -p "$SCHEMA_DIR"
cp "$ROOT/data/io.github.fedoranova.FedoraNova.Devel.gschema.xml" "$SCHEMA_DIR/"
if command -v glib-compile-schemas >/dev/null 2>&1; then
  glib-compile-schemas "$SCHEMA_DIR"
  export GSETTINGS_SCHEMA_DIR="$SCHEMA_DIR"
fi

exec python3 -m fedora_nova.application
