# Contributing to Fedora Nova

Fedora Nova is currently under active development. Changes should be small,
reviewable and tested before they are merged into the integration branch.

## Repository structure

```text
app/        GTK4/libadwaita Settings application
core/       Fedora Nova runtime, CLI, themes and desktop integrations
docs/       project and development documentation
.github/    CI configuration
tests/      development and regression tests
```

Development entry points currently remain in the repository root.

## Development setup

Install the required Fedora development dependencies:

```bash
./dev-setup-fedora.sh
```

For the full Builder workflow, GNOME Platform/SDK 50 must also be available to
Flatpak.

## Development modes

Fedora Nova keeps preview, host and Shell development paths intentionally
separate.

### Native Preview

Run:

```bash
./dev-run.sh preview
```

Native Preview:

- runs from the current checkout,
- uses the current checkout `core/`,
- uses the current checkout Shell Preview helper,
- isolates Fedora Nova preview state under `.dev-build/preview-config/`,
- does not intentionally modify the active host GNOME configuration.

Do not weaken the preview/host boundary to make testing more convenient.

### Native Host

Run:

```bash
./dev-run.sh host
```

Native Host uses the current checkout and can modify the active GNOME
environment.

Host mode is intended only for explicit real-system integration testing.

Development changes must not rely on a stale globally installed
`fedora-nova` executable when a current-checkout CLI is available.

### GNOME Builder / Flatpak Preview

Open the repository root:

```bash
gnome-builder .
```

Builder uses:

```text
io.github.fedoranova.FedoraNova.Devel.json
```

The development Flatpak is Preview-only.

Do not add a Flatpak-to-host bridge or `org.freedesktop.Flatpak` host-spawn
permission merely to expose Host mode from inside Builder. Real host integration
belongs in Native Host.

### GNOME Shell Preview

Run a nested Shell preview:

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

The preview uses Mutter Development Kit and an isolated configuration.

Selective theme hot reload should remain conservative: unsafe or unsupported
changes must fall back to a full nested Shell restart rather than weakening the
reload safety checks.

## Settings application

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

For Builder workflow changes also run:

```bash
python3 -m unittest -v tests.test_builder_workflow
```

For hot-reload changes run:

```bash
python3 -m unittest -v tests.test_theme_hot_reload
```

For lifecycle-sensitive Shell Preview changes run the opt-in suite:

```bash
NOVA_LIFECYCLE_TESTS=1 \
python3 -m unittest -v tests.test_theme_hot_reload
```

## Meson and packaging validation

Do not reuse a manual Meson build directory across different Meson versions.

The host system and GNOME SDK may ship different Meson releases, so use
development-only test directories:

```bash
rm -rf \
  .dev-build/meson-test \
  .dev-build/meson-staging

meson setup .dev-build/meson-test
meson compile -C .dev-build/meson-test

DESTDIR="$PWD/.dev-build/meson-staging" \
  meson install -C .dev-build/meson-test
```

For Flatpak packaging changes:

```bash
rm -rf .flatpak-build-test

flatpak-builder \
  --force-clean \
  --user \
  --install \
  .flatpak-build-test \
  io.github.fedoranova.FedoraNova.Devel.json
```

Development-only files must not leak into installed runtime data.

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

Do not use `git add .` when a change contains unrelated local work. Stage the
intended files explicitly and inspect the cached diff before committing.

## Safety

Changes affecting host GNOME settings, extensions, themes or user configuration
must provide a safe failure path where practical.

Preview infrastructure should remain isolated from the normal host environment.

Flatpak Preview must remain Preview-only unless the project deliberately changes
that security model in a separately reviewed change.

Do not weaken Shell Preview identity, recovery, transaction or process-cleanup
checks to make live reload simpler.

Do not commit personal absolute paths, local Builder state, caches, generated
bytecode or build directories.