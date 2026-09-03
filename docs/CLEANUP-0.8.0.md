# Fedora Nova 0.8.0 cleanup notes

This branch is intentionally refactored in small, reviewable steps.

Current priorities:

1. Keep runtime appearance unchanged while cleanup infrastructure is added.
2. Make preview iteration faster and quieter.
3. Add golden checks before migrating GNOME Shell styling fully to SCSS.
4. Consolidate profile/color sources and Settings implementations only after behavior is covered.

Safety baseline: `cleanup/0.8.0-safety-backup`.
