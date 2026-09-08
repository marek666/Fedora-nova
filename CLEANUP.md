# Fedora Nova 0.8.0 cleanup

## Completed

- [x] move GTK4/libadwaita application into `app/`
- [x] move application metadata into `app/data/`
- [x] update native development paths
- [x] update static check paths
- [x] remove obsolete HTML preview
- [x] remove stale checksum manifests
- [x] remove committed personal `.buildconfig`
- [x] flatten project documentation
- [x] move concept media out of runtime assets
- [x] refresh README
- [x] standardize current development version to `0.8.0-dev`
- [x] remove obsolete CLI HTML preview command

## Current

- [ ] verify cleaned Meson application hierarchy
- [ ] rebuild GNOME Builder development workflow
- [ ] verify Flatpak Preview after repository restructuring
- [ ] document final Builder native and host commands
- [ ] merge and relocate completed Shell hot-reload infrastructure
- [ ] reduce GNOME Shell CSS parser warnings

## Later

- [ ] make `VERSION` the canonical project version source
- [ ] consolidate legacy and modern Settings implementations
- [ ] make terminal integration first-class in CLI and Settings
- [ ] separate remaining development-only tooling from installed runtime
- [ ] consolidate profile and color configuration sources