# Dash to Dock stage sizing in Shell Preview

Dash to Dock 105 exposes its dash to GNOME startup layout before attaching it
at `startup-complete`. The captured stack reaches `dash.js` preferred width
from `overviewControls.js` startup animation. St then requests theme nodes on
actors outside the stage. A second path measures the outer dock through the
replacement for the original dash preferred height in `docking.js`.

`dev-tools/prepare_preview_dock.py` copies the installed version 105 into the
isolated preview extension directory and applies three guards. No system or
host extension is edited. The equivalent review patch is
`dev-tools/dash-to-dock-stage-guards.patch`. Already-applied guards are accepted;
unexpected version-105 source fails before installing the copy. Other versions
use the installed extension unchanged with an explicit message. Re-evaluate
this workaround when upgrading the extension.

Measured on GNOME Shell/Mutter 50.4 with the Tech profile and a bottom dock:

| Variant | Stage warnings at startup |
| --- | ---: |
| Original | 213 |
| Guard in docking.js only | 207 |
| Guards in dash.js only | 6 |
| All three guards | 0 |

The combined variant enabled successfully and a real SCSS edit reached the live
CSS with the same Shell PID and zero stage warnings after reload. The inner
dash measured 489 × 78 pixels before and after the fix. Tests used isolated
Mutter Devkit sessions and their own cache; no main repository or system
extension was modified during the comparison. Multi-monitor, screen locking
and full interactive behavior have not been verified.

The helper is development-only and lives outside the packaged `core/` tree.
