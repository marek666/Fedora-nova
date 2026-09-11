# Fedora Nova 0.8.0 cleanup

## Status

The structural cleanup phase for the 0.8.0-dev baseline is complete. New work
should default back to product/runtime features unless a concrete regression or
release blocker requires another cleanup change.

## Completed

- [x] move GTK4/libadwaita application into `app/`
- [x] move application metadata into `app/data/`
- [x] standardize current development version to `0.8.0-dev`
- [x] rebuild and verify GNOME Builder Native Preview/Host workflow
- [x] keep Flatpak Preview isolated from host integration
- [x] integrate nested GNOME Shell hot reload around the current checkout
- [x] establish canonical package runtime layout under `share/fedora-nova/`
- [x] retire the legacy Settings frontend and deprecated CLI aliases
- [x] make production and development Settings identities explicit
- [x] protect canonical package layout from standalone compatibility scripts
- [x] add guarded legacy-to-canonical installation migration
- [x] bind session restore to the physical canonical runtime
- [x] separate immutable bundled config from mutable XDG user state
- [x] consolidate Forge template colors on canonical profile data
- [x] improve GTK3 compatibility styling and regression coverage
- [x] remove obsolete source/runtime assets and duplicate terminal palette data
- [x] harden ownership checks for legacy wrappers, desktop entries and Ptyxis data
- [x] keep source-only development files out of canonical and standalone payloads
- [x] run the full default regression suite in CI with required dependencies
- [x] keep Shell Preview development checkout-local instead of installing a global helper

## Intentional compatibility surface

These paths remain on purpose and are not cleanup debt for 0.8.0-dev:

- `core/install.sh` and `core/uninstall.sh` for the core-only standalone compatibility path
- `core/scripts/install-assets.sh` for the standalone CLI wrapper integration
- `core/scripts/migrate-installation.sh` for guarded migration to canonical package layout
- historical uninstall recognition needed to remove known Fedora Nova-owned artifacts safely

They can be retired in a future compatibility-breaking release after that policy is decided.

## Non-blocking follow-up

- [ ] reduce remaining GNOME Shell CSS parser/compatibility warnings
- [ ] make root `VERSION` the generated/canonical source for every version consumer
- [ ] recheck the verified development workflow from a completely fresh clone before release
- [ ] decide the release window for removing standalone/core-only compatibility
