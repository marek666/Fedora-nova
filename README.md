# Fedora Nova

Fedora Nova is an experimental desktop appearance and control project for Fedora GNOME.

The project combines a GNOME Shell theme, configurable visual profiles, desktop integration, a GTK4/libadwaita Settings application, and an isolated nested GNOME Shell development preview.

> Current development version: **0.8.0-dev**
>
> Fedora Nova is under active development. Host mode can modify the current GNOME session; use Preview mode for normal UI development.

## Project structure

```text
app/        GTK4/libadwaita Fedora Nova Settings application
core/       runtime, CLI, themes, profiles and desktop integrations
docs/       design, Builder workflow, roadmap and development notes
.github/    CI
```

Development entry points remain in the repository root and use the current checkout directly.

## Development

See [development integration and next steps](docs/DEVELOPMENT-PLAN.md) for the
current workflow, ownership rules, and release verification checklist.

Install the Fedora development dependencies:

```bash
./dev-setup-fedora.sh
```

Run the Settings application in safe preview mode:

```bash
./dev-run.sh preview
```

Run the Settings application against the host backend:

```bash
./dev-run.sh host
```

Develop the theme in an isolated nested GNOME Shell with automatic reload:

```bash
./dev-shell-preview.sh --watch tech
```

Close the Mutter Development Kit window, or stop it explicitly:

```bash
./dev-shell-preview.sh --stop
```

The launcher builds from its own checkout and keeps per-profile settings in
`~/.cache/fedora-nova-shell-preview`. See [Shell Preview](docs/BUILDER.md#nested-gnome-shell-preview)
for cache boundaries and isolated test sessions.

### Blur My Shell integration

Fedora Nova leaves Blur My Shell enabled and uses it for its blur effects. To
avoid its competing overview hover and component colors, the integration sets
`org.gnome.shell.extensions.blur-my-shell.overview style-components` to `0`.
This removes BMS component styling for the app grid, search results, search
entry, workspace thumbnails, and related overview controls. Nova and the Shell
theme then provide their appearance. It does not change BMS blur strength,
brightness, noise, or which BMS blur features are enabled.

The helper is:

```bash
core/scripts/integrations/blur-my-shell.sh [status|apply|restore]
```

`status` only reports the current setting and saved value. `apply` is the
default action: on its first run it saves the current setting, changes it to
`0` when necessary, and reads it back to confirm the change. Later runs retain
the original backup. `restore` returns the saved value only when the current
value is still `0` or already equals that backup; it preserves a conflicting
manual nonzero choice instead.

The saved value lives at:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/fedora-nova/integrations/blur-my-shell/previous-style-components
```

The nested Shell preview runs `apply` after entering its isolated configuration
and D-Bus session, before GNOME Shell starts. Its backup is therefore separate
from the host at:

```text
<preview-root>/config/fedora-nova/integrations/blur-my-shell/previous-style-components
```

The host profile application, configuration import, and snapshot restore also
run `apply`. Import and snapshot restore run it before and after loading BMS
dconf data. The first call ensures that a pre-Nova backup exists without
overwriting an existing backup; the second re-enforces Nova compatibility after
the imported data is loaded. The installer reaches the same path through
`apply-preset`; `--no-apply` installs files without changing BMS settings.

Normal uninstallation runs `restore` before removing Nova configuration. With
`--restore`, the full dconf backup is authoritative and restores BMS together
with the rest of the desktop settings. Nova never enables BMS itself, so an
extension disabled by the user remains disabled. Safe mode still deliberately
disables it.

The helper checks the global GSettings schema first and then a locally
installed BMS schema under `$XDG_DATA_HOME`. If neither is available, it reports
that the integration is skipped and makes no changes. A requested `apply` or
`restore` fails when the setting is not writable or its result cannot be read
back.

## Checks

```bash
./check.sh
```

The check script validates Bash, Python, Sass, JSON, and XML sources.

## Fedora Nova Core

The runtime lives in:

```text
core/
```

The CLI entry point is:

```bash
core/nova --help
```

Fedora Nova currently provides profiles, dock settings, motion presets, corner curves, hover styles, GTK integration, icon themes, Steam icon handling, multi-monitor panel support, snapshots, configuration import/export, and diagnostics.

## Themes

Built-in Shell themes:

- Fedora Nova Tech
- Fedora Nova Clean
- Fedora Nova Midnight
- Fedora Nova Glass Lite
- Fedora Nova Pulse

Development Sass sources live in:

```text
core/themes-src/
```

Compiled runtime themes live in:

```text
core/themes/
```

## Settings application

The Settings application lives in:

```text
app/src/fedora_nova/
```

Application metadata and GSettings resources live in:

```text
app/data/
```

It is built with GTK4 and libadwaita.

## GNOME Builder

See:

```text
docs/BUILDER.md
```

The Builder workflow is tested for Fedora Nova 0.8.0-dev and keeps Flatpak Preview, Native Preview, Native Host, and Shell Preview intentionally separate.

## Documentation

- `CHANGELOG.md`
- `CLEANUP.md`
- `CONTRIBUTING.md`
- `docs/BUILDER.md`
- `docs/DASH-TO-DOCK-PREVIEW.md`
- `docs/DESIGN.md`
- `docs/DEVELOPMENT-PLAN.md`
- `docs/GTK.md`
- `docs/ROADMAP.md`
- `docs/SOURCES.md`
- `core/themes-src/README.md`
- `core/themes-src/scss/README.md`

## Branches

`main` contains stable releases.

`development` is the integration branch for the next release.

Feature and cleanup work is developed on dedicated branches before being merged into `development`.

## License

Fedora Nova is licensed under GPL-3.0-or-later.

See `LICENSE`.
