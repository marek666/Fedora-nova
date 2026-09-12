#!/usr/bin/env python3
from __future__ import annotations

import re
import sys

import theme_hot_reload_core as _core

USER_THEME_UUID = "user-theme@gnome-shell-extensions.gcampax.github.com"
_EXTENSION_API_MISSING = (
    "UnknownMethod",
    "UnknownObject",
    "UnknownInterface",
    "No such interface",
    "does not exist at path",
)

_original_set_theme = _core.ShellIdentity.set_theme


def _toggle_user_theme_extension(self, method: str, *, rollback: bool = False) -> bool:
    """Synchronously disable/enable User Themes inside the verified nested Shell.

    GNOME's User Themes extension calls Main.loadTheme() from disable()/enable().
    Using the Shell D-Bus extension API therefore gives the preview a real
    compositor-side reload boundary instead of racing two fast GSettings writes.
    Older/fake Shells without the interface fall back to the legacy setting
    toggle so the safety/recovery path remains testable.
    """
    self.verify(rollback=rollback)
    if self.env is None or not self.address:
        raise _core.HotReloadError("nested Shell D-Bus environment is unavailable")

    command = [
        "gdbus",
        "call",
        "--address",
        self.address,
        "--dest",
        "org.gnome.Shell",
        "--object-path",
        "/org/gnome/Shell",
        "--method",
        f"org.gnome.Shell.Extensions.{method}Extension",
        "--timeout",
        "1" if rollback else "3",
        USER_THEME_UUID,
    ]
    try:
        raw = _core.run_checked(
            command,
            env=self.env,
            timeout=0.35 if rollback else 3.5,
            ignore_cancel=rollback,
        )
    except _core.HotReloadError as exc:
        text = str(exc)
        if any(marker in text for marker in _EXTENSION_API_MISSING):
            return False
        raise

    if not re.fullmatch(r"\(true,\)", raw.strip()):
        raise _core.HotReloadError(
            f"User Themes {method.lower()} request was rejected: {raw or 'empty response'}"
        )

    self.verify(rollback=rollback)
    return True


def _set_theme_with_shell_reload(self, name: str, *, rollback: bool = False):
    # replace_live_theme() already uses set_theme('') / set_theme(theme) as its
    # transaction boundaries. On a real GNOME Shell, map those boundaries to
    # synchronous extension disable/enable calls. The configured theme name is
    # intentionally left unchanged while the extension is disabled.
    if name == "":
        if _toggle_user_theme_extension(self, "Disable", rollback=rollback):
            if not rollback:
                print(
                    "Theme reload: User Themes disabled in nested Shell; applying staged CSS.",
                    file=sys.stderr,
                )
            return
    elif name == self.theme:
        if _toggle_user_theme_extension(self, "Enable", rollback=rollback):
            if self.get_theme(rollback=rollback) != self.theme:
                raise _core.HotReloadError(
                    "User Themes re-enabled but configured theme name changed"
                )
            if not rollback:
                print(
                    "Theme reload: User Themes re-enabled; nested Shell loaded the staged theme.",
                    file=sys.stderr,
                )
            return

    return _original_set_theme(self, name, rollback=rollback)


_core.ShellIdentity.set_theme = _set_theme_with_shell_reload

# When imported by preview_reload/tests, expose the implementation module itself
# so monkeypatches keep affecting the globals used by its functions. When run as
# a script, execute the patched implementation directly.
if __name__ == "__main__":
    raise SystemExit(_core.main())

sys.modules[__name__] = _core
