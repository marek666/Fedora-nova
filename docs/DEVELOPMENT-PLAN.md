# Development integration and next steps

## Baseline inspected on 2026-09-12

The two local working directories are Git worktrees of the same repository,
`marek666/Fedora-nova`, rather than separate application and runtime repositories.
Keep `app/` and `core/` together so one revision describes the complete preview.
The following relationships were verified against local refs; fetch and check
the remote refs again before merging.

| Branch | Role and integration |
| --- | --- |
| `development` (`40568ad`) | Next-release integration base |
| `fix/preview-reload-persistence` (`dc448d7`) | Contains the current stability and synchronous reload changes; use as the next integration candidate, plus the startup SCSS fix |
| `fix/shell-preview-stability` (`ee0511d`) | Already an ancestor of the integration candidate |
| `origin/fix/shell-preview-reload` (`bc567c0`) | Already merged into the integration candidate |
| `theme/gtk3-csd-titlebar` (`bb3b6d3`) | One remaining commit outside the candidate, changing `core/scripts/gtk-theme.sh`; review separately after preview integration |

Do not merge the stability and reload branches again or copy files between
working directories. Submit the tested integration candidate to `development`,
then review the GTK3 branch against that updated base. Keep `main` for releases.
Retain old branches until integration and the interactive smoke checks pass.

## Daily development

Use a persistent checkout for `development` and a separate worktree per active
change, with branches such as `codex/hover-consistency`. Start the preview from
the same worktree that is open in the editor:

```bash
./dev-shell-preview.sh --watch tech
```

The startup banner prints the source directory. The preview runtime is shared
per user cache directory, so use one Shell Preview at a time when switching
worktrees. Stop the old preview before launching from a different worktree.

Startup, restart and incremental theme reload now build the selected theme with
the same staging function. Default `circle` and `squircle` modes use SCSS;
other selected modes apply the Python runtime generators over those layers.
Consequently, edits to `_hover-circle.scss` are visible with `circle` selected.
Editing `hover_style.py` does not override the default circle SCSS during reload.
Use `--reset-settings` deliberately if clean profile defaults are needed.

Generated staging output stays outside tracked runtime themes. Compile release
theme output intentionally with `core/scripts/build-theme-sass.sh --apply`.

## Delivery sequence

1. **Reliable preview and integration.** Verify a visible SCSS change after save,
   then after a forced restart and stop/start. Confirm profile settings survive,
   reload keeps the Shell PID, and unsafe changes still trigger a restart.
   Run `./check.sh`, the reload/bridge/refresh suites and opt-in lifecycle tests.
   Complete interactive verification before merging into `development`.
2. **Hover consistency.** Define the desired grid, dock and Show Applications
   appearance. Resolve duplicated SCSS/Python circle styling and the currently
   unused `grid_halo`/`dock_halo` renderer parameters. Check circle, compact, tile
   and none across built-in profiles, both after startup and live changes.
   Keep this visual change separate from reload lifecycle fixes.
3. **GTK3 titlebars.** Integrate and test the remaining GTK3 commit on the new
   base, including enabled/disabled GTK mode and existing GTK4 behavior.
4. **Release validation.** Run the complete regression suite and interactive
   Native Preview, explicit Host, Builder/Flatpak and Shell Preview checks from
   a clean checkout. Update the changelog and compiled themes before release.

Track each numbered item as a separate reviewable change with its acceptance
checks. Schedule the next feature only after the current item meets those
checks; the immediate priority is a trustworthy visual development loop.
