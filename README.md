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

Development entry points remain in the repository root while the 0.8.0 preview infrastructure is being stabilized.

## Development

See [development integration and next steps](docs/DEVELOPMENT-PLAN.md) for the
current branch integration order and preview verification checklist.

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

Run an isolated nested GNOME Shell:

```bash
./dev-shell-preview.sh tech
./dev-shell-preview.sh --watch tech
./dev-shell-preview.sh --stop
```

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

The Builder workflow is currently being cleaned up for Fedora Nova 0.8.0.

## Documentation

- `CHANGELOG.md`
- `docs/BUILDER.md`
- `docs/DESIGN.md`
- `docs/GTK.md`
- `docs/ROADMAP.md`
- `docs/SOURCES.md`

## Branches

`main` contains stable releases.

`development` is the integration branch for the next release.

Feature and cleanup work is developed on dedicated branches before being merged into `development`.

## License

Fedora Nova is licensed under GPL-3.0-or-later.

See `LICENSE`.
