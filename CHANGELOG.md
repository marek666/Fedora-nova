# Changelog

## 0.8.0-dev — Repository, preview and Builder workflow cleanup

- reorganized the GTK4/libadwaita application under `app/`,
- separated application sources and application data,
- moved project documentation into a clearer structure,
- removed obsolete HTML preview infrastructure,
- removed stale development checksum manifests,
- removed committed personal Builder configuration,
- updated development launchers for the new `app/` layout,
- updated static checks for the reorganized source tree,
- standardized current development version metadata to `0.8.0-dev`,
- integrated the tested selective GNOME Shell theme hot-reload implementation,
- added transactional and lifecycle hardening for the nested Shell Preview,
- kept full nested Shell restart as the conservative fallback for changes that
  cannot be applied live,
- rebuilt the GNOME Builder development workflow around the current checkout,
- made Native Preview use an isolated development configuration instead of the
  normal host Fedora Nova state,
- pinned Native Preview and Native Host to the current checkout CLI, core and
  Shell Preview helper,
- required explicit Host authorization for native Host mode,
- made native development instances independent from stale GApplication
  activation in another mode or worktree,
- made the development Flatpak permanently Preview-only,
- removed the development Flatpak host-spawn permission and disabled the
  Flatpak-to-host bridge,
- made Shell Preview unavailable from the development Flatpak,
- added Builder workflow regression tests,
- verified GNOME Builder 50 Build + Run with GNOME Platform/SDK 50,
- verified Flatpak build, install and AppStream composition,
- verified hot-reload unit and lifecycle suites after the Builder changes.

## 0.7.2-dev — Full System Setup

- added `fedora-nova preset full --reload`,
- added session restore autostart after login,
- full preset enables User Themes, Dash to Dock and Top Bar All Monitors,
- full preset configures Continuous Squircle, Circle Large hover, Tela Circle,
  circular Steam icons and Nova GTK/libadwaita colors,
- Mutter Development Kit preview starts with matching Nova layers.

## 0.6.4 — Dock Hover & Large Halo Fix

- rewrote the exact gray Dash to Dock hover selector,
- added higher-priority dock background, border and box-shadow rules,
- default Circle hover uses a 10 px app-grid halo and 5 px dock halo,
- halo no longer changes icon padding, margin or icon size,
- added `circle-compact`,
- fixed Show Applications hover,
- updated native Settings and Zenity fallback.

## 0.6.3

- moved hover styling to the shared icon container used by applications and
  folders.

## 0.6.2

- added SVG superellipse styling for expanded folder dialogs,
- stabilized hover geometry,
- fixed circular Steam icons.