# Development integration and next steps

## Current baseline

`development` is the integration branch for the next Fedora Nova release and `main` is reserved for stable releases. Keep `app/` and `core/` in the same revision so one commit describes the complete Settings, runtime and Shell Preview state.

Use dedicated feature or fix branches for isolated work and merge them back into `development` only after the relevant static, regression and interactive checks pass. Avoid copying files between worktrees or relying on globally installed development helpers when the current checkout provides them.

The 0.8.0-dev baseline already includes the repository cleanup, current-checkout Builder workflow, isolated Native Preview, explicit Native Host, Preview-only Flatpak development build, nested Mutter Development Kit Shell Preview, and selective theme hot reload.

## Daily development

Use a persistent checkout for `development` and a separate worktree per active change. Start the Shell Preview from the same worktree that is open in the editor:

```bash
./dev-shell-preview.sh --watch tech
```

The startup banner prints the source directory. The preview runtime is shared per user cache directory, so use one normal Shell Preview at a time when switching worktrees. Stop the old preview before launching from another worktree, or use a separate `XDG_CACHE_HOME` for an intentional second test session.

Preview startup, restart and incremental theme reload build the selected theme through the same staging pipeline. The default `circle` hover remains owned by Sass; non-default hover modes are applied by the Python runtime renderer. Edits to `_hover-circle.scss` should therefore be visible with `circle` selected.

Generated staging output stays outside tracked runtime themes. Compile release theme output intentionally with:

```bash
core/scripts/build-theme-sass.sh --apply
```

Invalid source markers or compilation errors must stop a fallback restart with a diagnostic rather than silently using stale checked-in CSS.

## Extension and appearance ownership

Fedora Nova owns visual appearance. Extensions should provide behavior and effects without competing theme layers where that can be configured safely.

For Blur My Shell, Fedora Nova keeps blur functionality intact and sets the overview `style-components` value to `0`. The integration stores the original value once and can restore it during uninstall without overwriting a conflicting manual change. Host mode and the isolated Shell Preview use the same integration helper but separate XDG configuration roots.

Dash to Dock remains responsible for dock behavior. Fedora Nova disables its custom theme layer where possible and owns the dock appearance through the Nova theme and profile settings.

## Current delivery sequence

1. **Visual consistency.** Continue aligning app-grid, dock, Show Applications, Quick Settings and related Shell surfaces across built-in profiles. Keep default hover styling in Sass and avoid extension-specific CSS wars when an extension exposes a clean compatibility setting.
2. **Integration verification.** For changes involving Blur My Shell, Dash to Dock or other extensions, verify both Native Host and isolated Shell Preview behavior, repeated application, manual user changes and uninstall/restore ownership.
3. **GTK compatibility.** Keep the managed GTK4/libadwaita color layer conservative and test the broader GTK3 compatibility layer, especially CSD titlebars and applications such as virt-manager.
4. **Release validation.** Run `./check.sh`, the complete regression/lifecycle suite, and the interactive Native Preview, Native Host, Flatpak Preview and Shell Preview smoke checks from a clean checkout. Update the changelog and compiled themes before release.

Track each item as a separate reviewable change with explicit acceptance checks. Prefer a trustworthy visual development loop over large mixed refactors.
