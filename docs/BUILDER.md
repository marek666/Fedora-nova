# GNOME Builder development

Fedora Nova supports GNOME Builder for development of the GTK4/libadwaita
Settings application.

The Builder workflow is being cleaned up for Fedora Nova 0.8.0.

## Open the project

Open the repository root in GNOME Builder.

The root `meson.build` loads the application through:

```text
app/
├── src/
└── data/
```

## Flatpak Preview

The development Flatpak manifest is:

```text
io.github.fedoranova.FedoraNova.Devel.json
```

It uses:

```text
org.gnome.Platform 50
org.gnome.Sdk 50
```

and launches:

```text
fedora-nova-settings-devel
```

This mode is intended primarily for safe Settings UI development.

## Native preview

Outside Builder, the canonical native preview command is currently:

```bash
./dev-run.sh preview
```

It runs the application directly from:

```text
app/src/
```

and uses the core from the current checkout:

```text
core/
```

## Native host mode

For actual Fedora Nova host integration use:

```bash
./dev-run.sh host
```

Host mode can modify the active GNOME configuration.

Until the Builder host command is rebuilt and tested for 0.8.0, this command is
the canonical host-development entry point.

Do not depend on an old globally installed `fedora-nova` executable when
testing code from the current checkout.

## Nested GNOME Shell

GNOME Shell themes are tested separately through Mutter Development Kit:

```bash
./dev-shell-preview.sh tech
./dev-shell-preview.sh --watch tech
./dev-shell-preview.sh --stop
```

The nested Shell uses an isolated preview configuration.

## Development Flatpak

Build manually with:

```bash
flatpak-builder   --force-clean   --user   --install   .flatpak-build-test   io.github.fedoranova.FedoraNova.Devel.json
```

The Flatpak is a Settings application preview. It is not a replacement for the
nested GNOME Shell preview.

## Meson test

After build-system changes run:

```bash
rm -rf _build _staging

meson setup _build
meson compile -C _build

DESTDIR="$PWD/_staging"   meson install -C _build
```

## Current 0.8.0 Builder cleanup goals

The remaining Builder work is:

1. define a deterministic current-checkout native preview command,
2. define a deterministic current-checkout host command,
3. prevent accidental use of stale globally installed Fedora Nova code,
4. verify Flatpak-to-host development integration,
5. document the final Builder commands only after they pass real tests.

Until these tasks are completed, use `dev-run.sh` as the authoritative native
development entry point.