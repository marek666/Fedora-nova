# Fedora Nova Roadmap

## 0.8.0-dev

Current development focus:

- return to visible GNOME Shell/theme and profile development,
- use the verified nested Shell preview and selective hot reload for fast visual iteration,
- improve theme consistency and compatibility on current GNOME releases,
- keep the GTK4/libadwaita Settings frontend and canonical runtime stable while features evolve,
- treat the remaining items in `CLEANUP.md` as deferred follow-up unless they become concrete blockers.

The structural repository cleanup is complete for the current 0.8.0-dev baseline. Cleanup is no longer the default workstream.

A fresh `development` clone has been verified with `./check.sh` and the complete 160-test regression/lifecycle suite. The remaining pre-release verification is the full interactive Preview/Host/Flatpak/Shell smoke on a clean checkout.

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
- Flatpak packaging and AppStream composition pass,
- fresh-clone static checks and the complete regression/lifecycle suite pass.

Remaining before calling Builder support release-stable:

- repeat the complete interactive Native Preview, Native Host, Flatpak Preview and Shell Preview workflow from a fresh clone,
- keep documentation synchronized with launcher and manifest behaviour,
- avoid sharing Meson build directories between host and SDK Meson versions,
- continue adding regression coverage when the development workflow changes.

## Settings application

Planned work:

- keep `app/` as the canonical Fedora Nova graphical frontend,
- keep GUI state and runtime backend clearly separated,
- improve diagnostics and host/preview status reporting,
- continue responsive GTK4/libadwaita UI development.

## Core

Planned work:

- improve recovery and diagnostics as concrete runtime needs appear,
- preserve the canonical runtime/source boundary established for 0.8.0-dev,
- avoid reopening compatibility cleanup unless it becomes a release blocker or an intentionally scheduled breaking change.

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
- improve profile consistency and visual coherence,
- reduce GNOME Shell CSS parser warnings as part of theme work rather than a separate cleanup phase,
- investigate Dash to Dock theme-node warnings when they affect visible theme behaviour,
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
