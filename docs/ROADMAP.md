# Fedora Nova Roadmap

## 0.8.0-dev

Current development focus:

- finish the repository and development workflow cleanup,
- stabilize GTK4/libadwaita Settings development,
- keep the Fedora Nova runtime and Settings frontend clearly separated,
- consolidate version and project metadata,
- remove obsolete and duplicated development infrastructure,
- improve automated checks and packaging validation,
- continue theme compatibility cleanup for current GNOME releases.

## Preview development

The current development workflow now provides:

- isolated Native Preview for GTK4/libadwaita Settings work,
- Native Host mode pinned to the current checkout,
- permanently Preview-only Flatpak development builds,
- isolated nested GNOME Shell through Mutter Development Kit,
- selective theme hot reload with conservative full-restart fallback,
- regression tests for Builder workflow isolation and current-checkout
  resolution.

Native Preview stores development state separately from the normal host Fedora
Nova configuration.

The development Flatpak intentionally has no host bridge. Real host integration
is tested through Native Host instead.

## GNOME Builder

Builder workflow implementation for 0.8.0-dev is now functionally complete on
the development branch.

Verified:

- GNOME Builder 50 opens the project,
- GNOME Platform/SDK 50 builds the development manifest,
- Builder Build + Run launches Flatpak Preview,
- Flatpak Host mode remains unavailable,
- current-checkout native launchers do not fall back to stale installed code,
- Native Preview and Native Host can run as independent development instances,
- Builder workflow regression tests pass,
- Flatpak packaging and AppStream composition pass.

Remaining before calling Builder support release-stable:

- repeat the complete workflow from a fresh clone,
- keep documentation synchronized with launcher and manifest behaviour,
- avoid sharing Meson build directories between host and SDK Meson versions,
- continue adding regression coverage when the development workflow changes.

## Settings application

Planned work:

- make `app/` the canonical Fedora Nova graphical frontend,
- remove remaining duplicated legacy Settings implementations when replacement
  coverage is complete,
- keep GUI state and runtime backend clearly separated,
- improve diagnostics and host/preview status reporting,
- continue responsive GTK4/libadwaita UI cleanup.

## Core

Planned work:

- simplify runtime scripts,
- consolidate configuration sources,
- improve recovery and diagnostics,
- continue separating development-only tooling from installed runtime files,
- eventually reduce duplicated legacy GUI/control entry points once the modern
  Settings application fully replaces them.

## Terminal integration

Planned first-class terminal support:

```text
fedora-nova terminal status
fedora-nova terminal list
fedora-nova terminal apply PROFILE
fedora-nova terminal fastfetch on
fedora-nova terminal fastfetch off
fedora-nova terminal restore
```

The Settings application should use the same backend as the CLI.

## Themes

Current state:

- selective theme hot reload is integrated,
- inotify and polling collectors are covered by lifecycle tests,
- full nested Shell restart remains the conservative fallback,
- the preview uses the current checkout and isolated Shell configuration.

Planned work:

- continue moving maintainable Shell styling to Sass sources,
- keep compiled CSS as the runtime artifact,
- reduce GNOME Shell CSS parser warnings,
- investigate Dash to Dock theme-node warnings separately from the reload
  mechanism,
- improve profile consistency,
- continue testing theme compatibility against current GNOME Shell releases.

## Packaging and runtime boundary

Planned work:

- keep development-only helpers out of installed runtime data,
- continue validating Meson staging and Flatpak packaging,
- make root `VERSION` the long-term canonical version source where practical,
- review which parts of `core/` remain required inside the Settings Flatpak as
  runtime/frontend separation becomes stricter.

## Future

Possible later features:

- finer hover strength and opacity controls,
- profile-specific GTK radius controls,
- richer profile editor,
- Steam icon exception editor,
- application theme exports,
- additional desktop integrations.