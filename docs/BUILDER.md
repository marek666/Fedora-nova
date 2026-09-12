# GNOME Builder development

Fedora Nova 0.8.0-dev provides a tested development workflow for the
GTK4/libadwaita Settings application, native host integration and an isolated
nested GNOME Shell preview.

The canonical project root is the repository root.

## Development modes

Fedora Nova intentionally keeps four development modes separate:

```text
GNOME Builder / Fedora Nova development
├── Native Preview
│   └── current checkout, isolated Settings state
├── Native Host
│   └── current checkout, real Fedora Nova host backend
├── Flatpak Preview
│   └── sandboxed GTK4/libadwaita UI preview
└── Shell Preview
    └── Mutter Development Kit + current checkout + hot reload
```

These modes are not interchangeable. In particular, the development Flatpak is
a preview sandbox and does not provide a host bridge.

## Open the project

Open the repository root in GNOME Builder:

```bash
gnome-builder .
```

The root `meson.build` loads the application through:

```text
app/
├── src/
└── data/
```

The development Flatpak manifest is:

```text
io.github.fedoranova.FedoraNova.Devel.json
```

The tested development environment uses:

```text
org.gnome.Platform 50
org.gnome.Sdk 50
```

and launches:

```text
fedora-nova-settings-devel
```

GNOME Builder 50 can build and run this manifest directly.

## Flatpak Preview

Builder Run uses the development Flatpak as a safe Settings UI preview.

The Flatpak is permanently restricted to Preview mode:

- `runtime_mode` remains `preview`,
- System Host is unavailable,
- Shell Preview is unavailable,
- environment overrides cannot enable Host mode,
- Fedora Nova host helpers are rejected by the backend,
- the manifest does not grant `org.freedesktop.Flatpak` host-spawn access.

The manifest still sets:

```text
FEDORA_NOVA_PREVIEW=1
```

The Flatpak is therefore suitable for GTK4/libadwaita UI development, but it is
not the entry point for testing real host changes.

Manual build:

```bash
rm -rf .flatpak-build-test

flatpak-builder \
  --force-clean \
  --user \
  --install \
  .flatpak-build-test \
  io.github.fedoranova.FedoraNova.Devel.json
```

Manual run:

```bash
flatpak run io.github.fedoranova.FedoraNova.Devel
```

## Native Preview

Use:

```bash
./dev-run.sh preview
```

Native Preview always pins the development application to the current checkout:

```text
app/src/
core/
dev-shell-preview.sh
```

The launcher overrides development backend paths so a stale globally installed
Fedora Nova executable or helper cannot replace the current checkout.

Preview state is isolated under:

```text
.dev-build/preview-config/
```

This prevents Preview state from reading or overwriting the normal host
`~/.config/fedora-nova` state.

Native Preview also uses development-only non-unique GApplication behaviour so
it can run independently from another native development instance.

## Native Host

Use:

```bash
./dev-run.sh host
```

Native Host is the canonical way to test real Fedora Nova host integration from
the current checkout.

The launcher explicitly pins:

```text
FEDORA_NOVA_PROJECT_ROOT=<current checkout>
FEDORA_NOVA_CORE=<current checkout>/core
FEDORA_NOVA_CLI=<current checkout>/core/nova
FEDORA_NOVA_APP_DIR=<current checkout>/core
FEDORA_NOVA_SHELL_PREVIEW=<current checkout>/dev-shell-preview.sh
```

Host mode requires both of these conditions:

```text
FEDORA_NOVA_PREVIEW=0
FEDORA_NOVA_HOST_ALLOWED=1
```

`FEDORA_NOVA_PREVIEW=0` alone is not sufficient to enable Host mode.

Host mode can modify the active GNOME configuration. Use it only when a real
system integration test is intended.

Do not use a globally installed `fedora-nova` executable as a substitute for
the current checkout while developing.

## Nested GNOME Shell Preview

GNOME Shell themes are tested natively through Mutter Development Kit:

```bash
./dev-shell-preview.sh tech
```

Live watch mode:

```bash
./dev-shell-preview.sh --watch tech
```

Stop the preview:

```bash
./dev-shell-preview.sh --stop
```

The nested Shell uses isolated preview configuration under:

```text
~/.cache/fedora-nova-shell-preview/
```

The current development launcher prefers the Shell Preview helper from the
current checkout. A stale helper symlink from another worktree must not override
the explicitly selected helper.

The watch mode supports selective theme hot reload. Changes that cannot be
safely applied live fall back to a full nested Shell restart.

CSS/Sass changes use the User Themes extension API inside the verified preview
Shell. GTK refresh respects the saved on/off choice. Disabling User Themes
keeps it disabled even when CSS files change. Default circle hover uses matching
Python (startup) and Sass (reload) styling; non-default modes use the Python
renderer during reload too.

Settings persist per profile: both dconf (Mutter, dock and extension choices)
and `config/fedora-nova` (hover, curves, GTK, icon choice and custom profiles).
`--reset-settings tech` resets only that preview profile. The explicitly requested
profile still selects the Nova theme; it does not force extensions back on.

The nested Shell has a private `session-runtime` directory. The Devkit window
retains the parent Wayland and PipeWire connections, without sharing GNOME's
runtime marker files. This is a development preview, not an application security
sandbox.

The Shell Preview runtime and lock are intentionally shared between worktrees,
so the preview behaves as a single development session.

To review a worktree alongside the usual preview, use a separate cache root for
both start and stop:

```bash
XDG_CACHE_HOME=/tmp/fedora-nova-preview-test ./dev-shell-preview.sh --watch tech
XDG_CACHE_HOME=/tmp/fedora-nova-preview-test ./dev-shell-preview.sh --stop
```

Check a CSS edit without a Shell PID change, then change a dock preference and a
Nova hover/GTK choice and close/reopen the same preview. Those choices should
remain. Config/extension code changes may restart the preview; CSS edits should
not. The test cache above is temporary and may be cleared on reboot.

## Builder, native and Shell responsibilities

Use the modes for these tasks:

| Task | Recommended mode |
| --- | --- |
| GTK4/libadwaita layout and UI work | Builder Flatpak Preview |
| Safe native Settings development | `./dev-run.sh preview` |
| Real Fedora Nova host integration | `./dev-run.sh host` |
| GNOME Shell theme work | `./dev-shell-preview.sh --watch tech` |
| Flatpak packaging verification | `flatpak-builder` |

Do not add a Flatpak-to-host bridge merely to make Host mode available inside
Builder. Native Host is the intended host-development path.

## Development setup

Install Fedora development dependencies with:

```bash
./dev-setup-fedora.sh
```

This installs the native development tools used by Fedora Nova, including
Builder, Meson, Flatpak Builder, Sass tooling and Mutter Development Kit. It
does not install a global Shell Preview helper or bind development to one
worktree; run `./dev-shell-preview.sh` from the checkout you are testing.

## Checks

Run the normal project checks:

```bash
./check.sh
```

Run Builder workflow regression tests:

```bash
python3 -m unittest -v tests.test_builder_workflow
```

Run the normal theme hot-reload tests:

```bash
python3 -m unittest -v tests.test_theme_hot_reload
```

Run the full opt-in hot-reload lifecycle suite:

```bash
NOVA_LIFECYCLE_TESTS=1 \
python3 -m unittest -v tests.test_theme_hot_reload
```

## Meson staging test

For manual native Meson validation, do not reuse a build directory that GNOME
Builder or the Flatpak SDK may have created with a different Meson version.

Use development-only directories under `.dev-build/`:

```bash
rm -rf \
  .dev-build/meson-test \
  .dev-build/meson-staging

meson setup .dev-build/meson-test
meson compile -C .dev-build/meson-test

DESTDIR="$PWD/.dev-build/meson-staging" \
  meson install -C .dev-build/meson-test
```

This avoids build-directory incompatibility when the host Meson and the GNOME
SDK ship different Meson versions.

## Expected installed/runtime boundary

Development-only helpers must not be installed as normal Fedora Nova runtime
data.

Packaging checks should verify that staging does not contain development-only
items such as:

```text
theme_hot_reload.py
preview_reload.py
build-theme-sass.sh
themes-src/
tests/
*.pyc
```

## Verified 0.8.0-dev workflow

The current Builder workflow has been exercised with:

- GNOME Builder 50,
- GNOME Platform/SDK 50,
- Native Preview,
- Native Host backend resolution,
- Flatpak build/install/run,
- Builder Build + Run,
- Flatpak Host isolation,
- current-checkout path pinning,
- independent native development instances,
- Builder workflow regression tests,
- hot-reload unit and lifecycle tests,
- nested Mutter Development Kit Shell Preview.

Fresh-clone reproducibility should still be rechecked before declaring the
0.8.0 development workflow release-stable.
