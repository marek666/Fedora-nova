# Theme source

Fedora Nova keeps generated GNOME Shell CSS in `themes/`. The profiles share
the same performance-safe structure and differ mostly in palette and dock
presets. Large Quick Settings and Date Menu surfaces intentionally remain
opaque and shadow-free.

Reusable layers live in `themes-src/scss/` and compile to plain Shell CSS.
Use Sass for release-friendly source structure; avoid Tailwind here because
GNOME Shell CSS is not browser CSS and utility classes are not useful for St
selectors.

```bash
core/scripts/build-theme-sass.sh --check
core/scripts/build-theme-sass.sh --generate
core/scripts/build-theme-sass.sh --apply
```

`--apply` only replaces the `NOVA_CURVE` and `NOVA_HOVER` marker blocks inside
existing theme CSS files. Generated Sass output is written to `.dev-build/`, so
it is never part of the release payload.
