# Fedora Nova Sass sources

These SCSS files are source-only helpers for the GNOME Shell theme. They compile
to plain Shell CSS and are safe to ship only after compilation.

Tailwind is intentionally not used here. GNOME Shell CSS is not HTML/CSS in a
browser and does not have a DOM class pipeline, so utility classes would add a
build dependency without helping Shell selectors. Sass gives us variables,
profile maps and reusable layers while keeping the release artifact as normal
CSS.

Current Sass coverage:

- `NOVA_CURVE` layer,
- `NOVA_HOVER` circle layer,
- profile color tokens for the built-in themes.

Compile and validate the Sass layers:

```bash
core/scripts/build-theme-sass.sh --check
```

Generate files under `.dev-build/theme-sass`:

```bash
core/scripts/build-theme-sass.sh --generate
```

Replace the generated Sass layers inside `core/themes/*/gnome-shell.css`:

```bash
core/scripts/build-theme-sass.sh --apply
```
