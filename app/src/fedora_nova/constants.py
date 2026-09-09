from __future__ import annotations

import os
from pathlib import Path

DEVEL_APP_ID = "io.github.fedoranova.FedoraNova.Devel"
PRODUCTION_APP_ID = "io.github.fedoranova.FedoraNova"
# Identity never grants host access, and Flatpak always keeps the Devel schema.
APP_ID = (
    PRODUCTION_APP_ID
    if os.environ.get("FEDORA_NOVA_APP_ID") == PRODUCTION_APP_ID
    and os.environ.get("FEDORA_NOVA_PREVIEW") == "0"
    and os.environ.get("FEDORA_NOVA_HOST_ALLOWED") == "1"
    and not Path("/.flatpak-info").exists()
    else DEVEL_APP_ID
)
APP_NAME = "Fedora Nova Settings"
VERSION = "0.8.0-dev"
PROJECT_URL = "https://github.com/marek666/Fedora-nova"
ISSUE_URL = f"{PROJECT_URL}/issues"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("FEDORA_NOVA_PROJECT_ROOT", PACKAGE_DIR.parents[2]))
CORE_ROOT = Path(os.environ.get("FEDORA_NOVA_CORE", PROJECT_ROOT / "core"))
STYLE_PATH = PACKAGE_DIR / "style.css"
