# GNOME Shell performance audit — 2026-09-17

Scope: the current development working tree, GNOME Shell 50.4, host and an
already running nested Preview. Existing uncommitted theme/Preview changes were
preserved. This is not a completed frame-time benchmark of all Shell animations.

## Confirmed findings

The bundled Top Bar All Monitors extension destroyed every secondary panel on
every `monitors-changed` notification, including mode/geometry changes. Each
replacement constructs full upstream Panel, Calendar and Quick Settings objects.

The installed Shell resource `ui/dateMenu.js`, `MessagesIndicator` lines 761–778,
connects three message-tray signals and source count signals with `connect()`.
Its destroy handler disposes `_settings` but does not disconnect these callbacks.
A later notification callback dereferences the disposed settings. The host boot
journal contained 92 matching `_settings is null` JS errors. This establishes
the failure path, not the proportion of UI lag caused by it or the exact number
of leaked objects in the running host.

A characterization using the extracted installed class methods and mock emitters
retained 3/30/300 tray callbacks after destroying 1/10/100 indicators. One queue
change produced 1/10/100 exceptions. This is a lifecycle model, not a live Shell
heap measurement. Other unowned Calendar connections also need upstream review.

The local mitigation retains secondary panels by current monitor index, refreshes
their geometry, and only creates/removes panels for newly needed/obsolete slots.
For two monitors and 40 geometry changes, executing the actual old/new extension
reconciliation code with instrumented panel factories gave:

| Operation | Before | After |
| --- | ---: | ---: |
| Panel constructions, including initial panel | 41 | 1 |
| Panel destructions | 40 | 0 |

This avoids unnecessary actor/service construction and opportunities for the
upstream signal leak. It does **not** fix upstream cleanup on genuine panel
removal, primary-monitor changes requiring removal, or extension disable. It
cannot repair objects already leaked in a running host. No host installation or
system Shell source was changed, and no CSS or intended appearance was changed.

## Other inspected paths

- **Quick Settings / menus / CSS:** the Tech stylesheet disables shadows on
  Quick Settings and transitions on its toggles. Generic popup and Dock shadows,
  hover selector expansion, and animated rounded actors remain candidates for
  GPU/style profiling; none was demonstrated to cause the reported lag.
- **Calendar:** confirmed stale callback path above. Opening/closing a menu
  alone is not the same as destroying/recreating its indicator.
- **BMS:** absent from the host enabled-extension list. Preview enables it with
  panel and Dock blur false, Overview blur true. It therefore remains a candidate
  for Preview Overview cost, not evidence for current host Quick Settings lag.
  The Nova integration helper sets `overview/style-components`; it does not run
  per frame or add a live blur loop.
- **Folder Preview extension:** samples dock geometry every 100 ms only while
  a tracked folder is open. Allocation signals also invoke resize. Style writes
  compare the current value first. Geometry polling and allocation feedback are
  worth profiling during folder animation; no loop or measured stall was proved.
- **Watcher:** even in inotify mode it reconciles metadata every 500 ms for
  robustness. Twenty local `_scan_repo_state` calls over 227 entries had median
  3.24 ms, maximum 6.52 ms. It does not hash all content in that scan. Weakening
  the reconciliation interval was not justified by this measurement.
- **Allocation warnings:** 1,214 unnamed-actor warnings in the host boot journal.
  The message does not identify the responsible extension or measure frame cost;
  it is not sufficient grounds for changing Dash to Dock or theme rendering.

## Measurements and validation

One 10-second observational `/proc/PID/stat` sample (CPU percentage of one core):

| Process | CPU | End RSS |
| --- | ---: | ---: |
| Host Shell | 15.9% | 542.7 MiB |
| Nested Preview Shell | 0.1% | 346.7 MiB |
| Preview watcher | 1.2% | 23.3 MiB |

These were concurrent observations, not identical workloads or before/after
frame-time measurements. RSS from a single sample cannot establish a memory leak.

- PASS: `python3 -m pytest -q tests/test_monitor_panel_lifecycle.py` exercises
  reuse, geometry changes, primary change, hotplug, zero monitors, disable and
  re-enable using the actual reconciliation code and mocked Shell objects.
- PASS: old/new construction-count comparison described above.
- PASS: `bash -n dev-shell-preview.sh core/scripts/monitor-panel.sh`.
- PASS: `./check.sh`.
- Full suite inside the sandbox encountered a denied D-Bus socket in the Builder
  test; this is an environment restriction, not a panel assertion failure.
- PASS: `python3 -m pytest -q` outside the sandbox: 214 passed, 6 skipped,
  one existing GLib deprecation warning.
- PASS: `git diff --check`.
- NOT MEASURED: usable Sysprof frame trace. A bounded `sysprof-cli --gnome-shell
  --no-perf --no-debuginfod --no-network --no-disk --no-battery` attempt did not
  finalize before the stop deadline. `sysprof-cat` reported no usable callgraph.
  The incomplete capture must not be used as performance evidence.
- NOT TESTED visually: repeated Quick Settings/Calendar opens, popup and Dock
  animations, hover, Overview, BMS A/B, monitor hotplug and Preview restart with
  this patch. The running Shells rejected `org.gnome.Shell.Eval`; their debugging
  security settings were not relaxed. No frame timing or input replay was obtained.
- NOT TESTED: long-duration Preview/heap growth and frame-time before/after.

The prior claim that the secondary panel lifecycle was fully safe was too strong.
The next useful trace is a controlled nested session with repeatable menu actions
and frame timing, comparing stock theme, Nova theme, and BMS independently. A
broader panel or upstream Calendar replacement is not justified by this audit.
