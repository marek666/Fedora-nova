# Fedora Nova Installer V2

Installer V2 is the supported host reinstall/upgrade path for a source checkout.
It deliberately requires an explicit action and never treats the nested Shell
Preview as a host installation.

Start with the read-only plan:

```bash
./install.sh --dry-run
```

The output is grouped into `BACKUP`, `REMOVE`, `REPLACE`, `INSTALL`,
`SETTINGS`, `UNCHANGED`, and `WARNINGS`. Dry-run does not create a log, staging
directory, backup, or state file and does not invoke `dconf` or desktop cache
tools. The launcher also disables Python bytecode generation, so inspection
does not write `__pycache__` into the checkout.

After reviewing that plan, a real user-local install is explicit:

```bash
./install.sh --install
```

Do not run the installer with `sudo`. It installs into the current user's
`HOME`, XDG roots, and `${FEDORA_NOVA_INSTALL_PREFIX:-$HOME/.local}`. It does
not install or remove RPM packages and never writes to `/usr`.

## Transaction

The install sequence is:

```text
DISCOVER
  -> BUILD CURRENT PAYLOAD
  -> BACKUP
  -> CLEAN OLD FEDORA NOVA
  -> FRESH INSTALL CURRENT VERSION
  -> RESTORE / MIGRATE USER SETTINGS
  -> REFRESH DESKTOP CACHES
  -> VALIDATE
```

The payload is built only from reviewed runtime sources. In a Git checkout,
untracked files below `core/` are excluded as well. Source Sass,
development Preview helpers, bytecode, the legacy core installer/uninstaller,
and package lists are excluded. Each managed top-level target is copied to a
temporary sibling and atomically renamed into place. Shared directories such as
`applications`, `themes`, `icons`, `glib-2.0/schemas`, and
`gnome-shell/extensions` are never recursively replaced.
Relocated links are validated both against the whole staging tree and against
the independently installed component boundary.

If installation fails after the backup, the installer prints the exact backup
and rollback command. It does not automatically roll back a partly installed
host.

Install, rollback, and uninstall take one non-blocking per-user transaction
lock. A second mutating operation fails before changing managed host content;
its ownership plan is recomputed after the lock is held.

## State, logs, and backups

The default state root is:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/fedora-nova/
```

It contains:

```text
install-manifest.json   exact managed targets, tree entries, modes and hashes
install-state.json      last transaction and validation result
logs/                   install, rollback and uninstall logs
backups/TIMESTAMP/      immutable transaction backups
```

Every backup has a `backup.json` containing the Fedora Nova version, Git
commit, timestamp, Fedora/GNOME metadata when available, original target types,
checksums, symlink targets, preserved preference files, and targeted dconf
dumps. A backup directory is created with a unique microsecond timestamp and is
never overwritten.

Rollback is explicit:

```bash
./install.sh --rollback "$HOME/.local/state/fedora-nova/backups/TIMESTAMP"
```

Before rollback modifies anything, it creates another backup of the current
state. Rollback accepts only an owner-controlled, direct, non-symlink child of
the configured V2 backup root, rejects linked internal object/settings
directories, and restores only registered transaction paths listed in its
metadata. Preserved settings and dconf are not automatically replayed: V2 does
not modify them, so replaying an older snapshot could overwrite newer user
choices. Their verified backup copies remain available for explicit recovery.

## Validation

Run validation at any time:

```bash
./install.sh --validate
```

Validation checks the manifest and every managed target, file hashes and modes,
missing or unexpected targets, broken/escaping symlinks, source-checkout and
Preview links, ownership, known legacy duplicates, the GNOME Shell extension,
and readable relevant GNOME settings. A real managed-file failure exits
nonzero. Missing optional live-session checks are warnings.

## Uninstall

V2 uninstall is manifest-driven. Inspect it first:

```bash
./install.sh --uninstall-dry-run
```

Then, if wanted:

```bash
./install.sh --uninstall
```

It backs up and removes only manifest-owned targets. Fedora Nova preference
files, custom profiles/themes/wallpapers/palettes, generated Steam icons, logs,
and backups remain available. The emitted backup can restore the installation.

## Ownership model

### Fedora Nova managed program files

- canonical runtime: `$XDG_DATA_HOME/fedora-nova`;
- `fedora-nova`, `fedora-nova-settings`, and development Settings launchers in
  the configured user prefix;
- Fedora Nova desktop entries, AppStream metadata, schemas and app icons;
- five built-in `Fedora-Nova-*` Shell themes;
- bundled Fedora Nova wallpaper files;
- five built-in Ptyxis palettes and the Fastfetch configuration;
- the three bundled Tela Circle variants, including the Nova trash overlay;
- `topbar-all-monitors@fa8i.github.io`, which is the one Shell extension source
  owned by Fedora Nova.

The manifest records these exact targets. Files removed from a future payload
become stale manifest targets and are backed up before removal.

### Preserved user settings

- `current-*` and `previous-*` selections under
  `$XDG_CONFIG_HOME/fedora-nova`;
- custom profile JSON, `Fedora-Nova-Custom-*` themes, `custom-*.svg`
  wallpapers and custom Ptyxis palettes;
- generated `Fedora-Nova-Steam` icons and their state;
- Fedora Nova GTK blocks as part of the user's complete GTK 3/4 CSS files;
- session restore/autostart state, welcome overrides, and the initial setup
  marker;
- Blur My Shell's saved pre-Nova `style-components` value;
- targeted dconf trees for interface, window manager, background, screensaver,
  Shell, User Themes, Dash to Dock, and Blur My Shell.

Installer V2 does not load those dumps during install or rollback, because the
transaction itself does not reset them. They remain unchanged and the dumps
are retained for explicit recovery. Unknown values are reported rather than
silently replaced.

### Third-party files

Dash to Dock and Blur My Shell extension source directories are third-party and
are never deleted or patched by the host installer. Other themes, icons,
extensions, applications and files alongside Fedora Nova targets are untouched.
An unrecognized file at an old single-file Fedora Nova path is reported and
preserved. Product-prefixed wildcard leftovers that are not proven by a V2
manifest are also reported rather than deleted; this avoids claiming a
user-created `Fedora-Nova-*` theme, `fedora-nova-*` wallpaper, or similarly
named palette merely from its filename.

## Current and legacy footprint audit

Repository scripts and history identify these host layouts:

- standalone and canonical runtime at `$XDG_DATA_HOME/fedora-nova`;
- legacy and canonical launchers below `$HOME/.local/bin` or the configured
  prefix;
- built-in themes below `$XDG_DATA_HOME/themes`, including obsolete
  `Fedora-Nova` and the current five variants;
- wallpapers below `$XDG_DATA_HOME/backgrounds/fedora-nova`;
- Tela and generated Steam icons below `$XDG_DATA_HOME/icons`;
- app icons below `$XDG_DATA_HOME/icons/hicolor/scalable/apps`;
- top-panel extension below
  `$XDG_DATA_HOME/gnome-shell/extensions/topbar-all-monitors@fa8i.github.io`;
- Ptyxis palettes below `$XDG_DATA_HOME/org.gnome.Ptyxis/palettes`;
- Fastfetch data below `$XDG_CONFIG_HOME/fastfetch`;
- mutable choices, custom profiles, session launcher and BMS ownership record
  below `$XDG_CONFIG_HOME/fedora-nova`;
- GTK layers in `$XDG_CONFIG_HOME/gtk-3.0/gtk.css` and `gtk-4.0/gtk.css`;
- session/welcome desktop overrides below `$XDG_CONFIG_HOME/autostart`;
- older desktop entry `fedora-nova-control.desktop`, obsolete generic Ptyxis
  palette `Fedora Nova.palette`, and shadow copies of bundled
  `colors.json`, `profiles.json`, and `curves.json`;
- historical product-named themes under `$HOME/.themes`, treated as legacy
  Fedora Nova targets.

`$HOME/.icons/Tela-*` is only reported: repository history does not establish
exclusive Fedora Nova ownership of that deprecated third-party location.
System extension paths under `/usr/share` are read-only dependencies and never
cleanup targets.

The nested development Preview at
`$XDG_CACHE_HOME/fedora-nova-shell-preview` is explicitly outside the host
installer. Preview-only Dash to Dock staging/patches, isolated extensions,
dconf, D-Bus services and HOME data are neither discovered as host files nor
backed up or removed by V2.

## Path and symlink safety

All write/remove targets must be absolute descendants of an explicit canonical
HOME/XDG/prefix root. `/`, HOME itself, an XDG root itself, empty paths, Preview
paths, and targets with a symlinked parent are rejected. Leaf symlinks are
backed up as links and unlinked without following them. Recursive copy and
removal never follow symlinks. Existing objects selected for backup, replacement,
or removal must be owned throughout by the invoking user; unexpected ownership
or unsafe writable installer-state directories stop the transaction.

The bundled Tela archive is validated against absolute paths, `..`, special
files and escaping links before extraction. Its historical `CherryStudio.svg`
link contains one trailing newline in archive metadata; staging removes only
that CR/LF defect, then validation still rejects every dangling or escaping
managed link.
