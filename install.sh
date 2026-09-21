#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(realpath -e -- "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"

unset PYTHONPATH
exec python3 -I -c \
  'import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = ["install.sh", *sys.argv[2:]]; runpy.run_module("installer.cli", run_name="__main__")' \
  "$ROOT" "$@"
