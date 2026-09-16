# GTK integration

Fedora Nova does not replace the system GTK or libadwaita theme. Instead, when GTK integration is enabled, it manages a clearly delimited Fedora Nova block inside the user's GTK4 and GTK3 CSS files:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/gtk-4.0/gtk.css
${XDG_CONFIG_HOME:-$HOME/.config}/gtk-3.0/gtk.css
```

The managed block is wrapped by `NOVA_GTK_START` and `NOVA_GTK_END` markers. Existing user CSS outside those markers is preserved. `fedora-nova gtk off` removes only the Fedora Nova block.

## GTK4 / libadwaita

The GTK4 layer is intentionally conservative. It sets profile-derived libadwaita color variables for windows, views, header bars, sidebars, cards, dialogs, popovers and related surfaces. It also applies a 16 px radius to a small set of common widgets such as cards, boxed lists, popovers, entries and buttons.

The goal is color and shape consistency without replacing libadwaita or maintaining a complete custom GTK4 theme.

## GTK3 compatibility

The GTK3 layer is broader because classic GTK3 applications do not expose the same libadwaita variables. Fedora Nova provides profile colors for common windows, views, selections, menus, toolbars, controls, notebooks, sidebars, scrollbars, switches and progress bars.

Client-side decorated GTK3 titlebars are styled explicitly, including applications such as virt-manager. Generic server-side decoration ownership is left to Mutter so Fedora Nova does not create mismatched foreground/background combinations on window frames it does not own.

## Commands

```bash
fedora-nova gtk on
fedora-nova gtk off
fedora-nova gtk refresh
fedora-nova gtk status
```

`on` and `refresh` regenerate the managed blocks from the active Fedora Nova profile. `off` removes them. Applications generally need to be reopened before the new GTK CSS is visible.

GTK changes should be visually smoke-tested after larger profile or compatibility updates, especially in both libadwaita applications and representative GTK3 applications.
