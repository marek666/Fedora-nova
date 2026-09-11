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

## Deferred follow-up

These are intentionally deferred so theme and feature development can continue now. Revisit them when the related subsystem is being changed or before a release where they become blockers.

- [ ] reduce remaining GNOME Shell CSS parser/compatibility warnings while evolving the theme
- [ ] make root `VERSION` the generated/canonical source for every version consumer
- [ ] recheck Native Preview, Native Host, Flatpak Preview and Shell Preview from a completely fresh clone before release
- [ ] run a real GTK3 visual smoke test on applications such as virt-manager after larger GTK/theme changes
- [ ] keep canonical package staging/install/uninstall and legacy migration paths covered by release smoke tests
- [ ] decide the compatibility window for removing standalone/core-only install and migration support
- [ ] revisit terminal integration as a first-class Settings/CLI feature instead of compatibility-era asset copying
- [ ] periodically audit third-party bundled assets and GNOME extension compatibility when upstream versions change

## Development direction

The next default workstream is visual/theme and product development, not repository cleanup. Structural cleanup should only resume for a concrete regression, release blocker, or a deliberately scheduled compatibility-breaking change.
