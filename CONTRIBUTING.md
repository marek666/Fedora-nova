# Contributing to Fedora Nova

Fedora Nova is currently under active development. Changes should be small,
reviewable, and tested before they are merged into the integration branch.

## Repository structure

```text
app/        GTK4/libadwaita Settings application
core/       Fedora Nova runtime, CLI, themes and desktop integrations
docs/       project and development documentation
.github/    CI configuration
```

Development entry points currently remain in the repository root.

## Development setup

Install the required Fedora development dependencies:

```bash
./dev-setup-fedora.sh
```

## Settings application

Run the GTK4/libadwaita Settings application in safe preview mode:

```bash
./dev-run.sh preview
```

Preview mode does not intentionally modify the current host GNOME session.

Run against the host backend:

```bash
./dev-run.sh host
```

Host mode can modify the active GNOME environment and should only be used
when real system integration needs to be tested.

Settings application sources live in:

```text
app/src/fedora_nova/
```

Important files include:

```text
app/src/fedora_nova/application.py
app/src/fedora_nova/window.py
app/src/fedora_nova/pages.py
app/src/fedora_nova/backend.py
app/src/fedora_nova/style.css
```

Application metadata, desktop integration and GSettings resources live in:

```text
app/data/
```

## GNOME Shell Preview

Fedora Nova provides an isolated nested GNOME Shell using Mutter Development Kit.

Run a preview:

```bash
./dev-shell-preview.sh tech
```

Run live watch mode:

```bash
./dev-shell-preview.sh --watch tech
```

Stop the preview:

```bash
./dev-shell-preview.sh --stop
```

The preview uses an isolated configuration and does not intentionally replace
the currently logged-in GNOME Shell.

## Shell themes

Development Sass sources live in:

```text
core/themes-src/
```

Compiled runtime themes live in:

```text
core/themes/
```

Check Sass sources:

```bash
core/scripts/build-theme-sass.sh --check
```

Apply generated Sass output when intentionally updating compiled themes:

```bash
core/scripts/build-theme-sass.sh --apply
```

Do not manually edit generated theme output when the same section is owned by
the Sass build pipeline.

## Fedora Nova Core

The development CLI entry point is:

```bash
core/nova --help
```

Runtime and host integration code lives primarily in:

```text
core/nova
core/scripts/
core/config/
core/themes/
core/terminal/
```

## Checks

Before committing changes run:

```bash
./check.sh
```

For Meson or packaging changes also run:

```bash
rm -rf _build _staging
meson setup _build
meson compile -C _build
DESTDIR="$PWD/_staging" meson install -C _build
```

## Responsive UI testing

For Settings application changes test at approximately:

- 360 px
- 480 px
- 720 px
- 1040 px

Adaptive Preview can be toggled with:

```text
Ctrl+Shift+M
```

Check that navigation remains usable and that Adwaita rows and controls do not
overflow at narrow widths.

## Branch workflow

`main` contains stable releases.

`development` is the integration branch for the next Fedora Nova release.

Use dedicated branches for isolated work, for example:

```text
feature/*
fix/*
cleanup/*
```

Avoid mixing large structural moves with unrelated runtime or concurrency
changes in the same commit.

## Commit scope

Prefer commits that represent one understandable change.

Examples:

```text
cleanup: reorganize application sources
docs: refresh Builder workflow
fix(preview): repair native development launcher
feat(terminal): add Ptyxis profile control
```

## Safety

Changes affecting host GNOME settings, extensions, themes or user configuration
must provide a safe failure path where practical.

Preview infrastructure should remain isolated from the normal host environment.

Do not commit personal absolute paths, local Builder state, caches, generated
bytecode or build directories.