# Sources and third-party components

## GNOME Shell styling

Fedora Nova maintains project-owned GNOME Shell theme layers and compatibility rules for the Shell and supported extensions. Runtime behavior is tested against the GNOME Shell versions targeted by the project.

## Blur My Shell

- Upstream: https://github.com/aunetx/blur-my-shell
- Extension UUID: `blur-my-shell@aunetx`
- Integration: optional; Fedora Nova does not bundle or enable Blur My Shell

Fedora Nova uses Blur My Shell for blur effects when the extension is already available. The compatibility helper disables only BMS overview component styling by setting `style-components` to `0`; blur strength, brightness, noise and feature enablement remain owned by Blur My Shell and the user.

## Tela Circle

- Upstream: https://github.com/vinceliuice/Tela-circle-icon-theme
- GNOME-Look: https://www.gnome-look.org/p/1359276/
- License: GPL-3.0-or-later
- Bundled archive and notice: `core/third-party/Tela-circle/`

## Top Bar All Monitors

- Upstream: https://github.com/fa8i/topbar-all-monitors
- GNOME Extensions: https://extensions.gnome.org/extension/10094/top-bar-all-monitors/
- License: GPL-3.0-or-later
- Bundled source and notice: `core/third-party/topbar-all-monitors/`

## GNOME color management

Fedora Nova only opens the standard GNOME Color panel. ICC profiles are not part of the Fedora Nova theme and should be assigned to the specific display or device they describe.
