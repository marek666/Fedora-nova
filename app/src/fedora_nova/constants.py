from __future__ import annotations

import os
from pathlib import Path

APP_ID = "io.github.fedoranova.FedoraNova.Devel"
APP_NAME = "Fedora Nova Settings"
VERSION = "0.7.2-dev"
PROJECT_URL = "https://github.com/fedoranova/FedoraNova"
ISSUE_URL = f"{PROJECT_URL}/issues"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("FEDORA_NOVA_PROJECT_ROOT", PACKAGE_DIR.parent.parent))
CORE_ROOT = Path(os.environ.get("FEDORA_NOVA_CORE", PROJECT_ROOT / "core"))
STYLE_PATH = PACKAGE_DIR / "style.css"
