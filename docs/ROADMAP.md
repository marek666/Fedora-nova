# Fedora Nova Roadmap

## 0.8.0-dev

Current development focus:

- clean and document the repository structure,
- stabilize GTK4/libadwaita Settings development,
- rebuild the GNOME Builder workflow,
- keep the Fedora Nova runtime and Settings frontend clearly separated,
- consolidate version and project metadata,
- remove obsolete and duplicated development infrastructure,
- improve automated checks and packaging validation.

## Preview development

The current cleanup branch provides:

- Settings Preview for GTK4/libadwaita UI work,
- Native Host mode for real Fedora integration,
- isolated nested GNOME Shell through Mutter Development Kit,
- smart source watching with conservative Shell restart behavior.

Selective theme hot reload has been implemented and smoke-tested on its dedicated
feature branch. It will be merged after the project-structure cleanup so that
concurrency and security changes stay separate from directory moves.

## Settings application

Planned work:

- make `app/` the canonical Fedora Nova graphical frontend,
- remove remaining duplicated legacy Settings implementations when replacement
  coverage is complete,
- keep GUI state and runtime backend clearly separated,
- improve diagnostics and host/preview status reporting.

## Core

Planned work:

- simplify runtime scripts,
- consolidate configuration sources,
- improve recovery and diagnostics,
- continue separating development-only tooling from installed runtime files.

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

Planned work:

- continue moving maintainable Shell styling to Sass sources,
- keep compiled CSS as the runtime artifact,
- reduce GNOME Shell CSS parser warnings,
- improve profile consistency,
- merge the tested selective theme hot-reload implementation,
- keep full Shell restart as the conservative fallback.

## Builder

Before declaring Builder support stable for 0.8.0:

- native preview must use the current checkout,
- host mode must use the current checkout,
- Flatpak Preview must remain reproducible,
- Shell Preview must remain isolated,
- the complete workflow must pass from a fresh clone.

## Future

Possible later features:

- finer hover strength and opacity controls,
- profile-specific GTK radius controls,
- richer profile editor,
- Steam icon exception editor,
- application theme exports,
- additional desktop integrations.