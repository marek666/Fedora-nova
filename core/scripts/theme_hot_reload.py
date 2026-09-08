#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

CURVE_BEGIN = "/* NOVA_CURVE_START */"
CURVE_END = "/* NOVA_CURVE_END */"
HOVER_BEGIN = "/* NOVA_HOVER_START */"
HOVER_END = "/* NOVA_HOVER_END */"
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{32}$")


class HotReloadError(RuntimeError):
    pass


def require_dir(path: Path, label: str) -> Path:
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise HotReloadError(f"{label} is not a directory: {path}")
    return path


def process_environ(pid: int) -> dict[str, str]:
    if pid <= 0:
        raise HotReloadError("invalid Shell PID")
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError as exc:
        raise HotReloadError(f"cannot read nested Shell environment: {exc}") from exc

    result: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        result[os.fsdecode(key)] = os.fsdecode(value)
    return result


def validate_shell(pid: int, token: str) -> dict[str, str]:
    if not TOKEN_RE.fullmatch(token):
        raise HotReloadError("preview token is missing or invalid")
    env = process_environ(pid)
    if env.get("NOVA_PREVIEW_TOKEN") != token:
        raise HotReloadError("nested Shell token does not match preview supervisor")
    if not Path(f"/proc/{pid}").exists():
        raise HotReloadError("nested Shell is no longer running")
    return env


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        if not detail:
            detail = f"exit status {completed.returncode}"
        raise HotReloadError(f"{' '.join(command)}: {detail}")
    return completed.stdout.strip()


def read_choice(path: Path, default: str) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    return value or default


def extract_block(text: str, begin: str, end: str, source: Path) -> str:
    start = text.find(begin)
    if start < 0:
        raise HotReloadError(f"missing marker {begin} in {source}")
    finish = text.find(end, start)
    if finish < 0:
        raise HotReloadError(f"missing marker {end} in {source}")
    if text.find(begin, start + len(begin)) >= 0:
        raise HotReloadError(f"duplicate marker {begin} in {source}")
    return text[start : finish + len(end)]


def replace_block(text: str, begin: str, end: str, block: str, target: Path) -> str:
    start = text.find(begin)
    if start < 0:
        raise HotReloadError(f"missing marker {begin} in {target}")
    finish = text.find(end, start)
    if finish < 0:
        raise HotReloadError(f"missing marker {end} in {target}")
    if text.find(begin, start + len(begin)) >= 0:
        raise HotReloadError(f"duplicate marker {begin} in {target}")
    return text[:start] + block + text[finish + len(end) :]


def apply_generated_layers(theme_css: Path, layers_css: Path) -> None:
    theme_text = theme_css.read_text(encoding="utf-8")
    layers_text = layers_css.read_text(encoding="utf-8")
    for begin, end in (
        (CURVE_BEGIN, CURVE_END),
        (HOVER_BEGIN, HOVER_END),
    ):
        block = extract_block(layers_text, begin, end, layers_css)
        theme_text = replace_block(theme_text, begin, end, block, theme_css)
    theme_css.write_text(theme_text, encoding="utf-8")


def build_staged_theme(
    repo_root: Path,
    core: Path,
    profile: str,
    theme: str,
    preview_config: Path,
    preview_state: Path,
) -> tuple[Path, Path]:
    source_theme = require_dir(core / "themes" / theme, "source theme")
    build_script = core / "scripts" / "build-theme-sass.sh"
    curve_script = core / "scripts" / "curve_style.py"
    hover_script = core / "scripts" / "hover_style.py"
    curves_json = core / "config" / "curves.json"
    profiles_json = core / "config" / "profiles.json"

    for path in (build_script, curve_script, hover_script, curves_json, profiles_json):
        if not path.exists():
            raise HotReloadError(f"required theme input is missing: {path}")

    run_checked([os.fspath(build_script), "--generate"])
    layers_css = repo_root / ".dev-build" / "theme-sass" / profile / "gnome-shell-layers.css"
    if not layers_css.is_file():
        raise HotReloadError(f"generated Sass layers are missing: {layers_css}")

    staging_root = Path(
        tempfile.mkdtemp(prefix="theme-hot-reload-", dir=preview_state)
    )
    try:
        staged_themes = staging_root / "themes"
        staged_theme = staged_themes / theme
        staged_themes.mkdir(parents=True)
        shutil.copytree(source_theme, staged_theme, symlinks=True)

        theme_css = staged_theme / "gnome-shell" / "gnome-shell.css"
        if not theme_css.is_file():
            raise HotReloadError(f"theme CSS is missing: {theme_css}")
        apply_generated_layers(theme_css, layers_css)

        nova_config = preview_config / "fedora-nova"
        curve = read_choice(nova_config / "current-curve", "squircle")
        hover = read_choice(nova_config / "current-hover", "circle")
        custom_profiles = nova_config / "custom-profiles"

        run_checked(
            [
                sys.executable,
                os.fspath(curve_script),
                "apply",
                curve,
                os.fspath(curves_json),
                os.fspath(staged_themes),
            ]
        )
        run_checked(
            [
                sys.executable,
                os.fspath(hover_script),
                hover,
                os.fspath(profiles_json),
                os.fspath(custom_profiles),
                os.fspath(staged_themes),
            ]
        )
        return staging_root, staged_theme
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def nested_gsettings_env(
    shell_env: dict[str, str],
    preview_home: Path,
    preview_config: Path,
    preview_data: Path,
    preview_state: Path,
) -> dict[str, str]:
    bus = shell_env.get("DBUS_SESSION_BUS_ADDRESS", "")
    if not bus:
        raise HotReloadError("nested Shell has no DBUS_SESSION_BUS_ADDRESS")

    env = os.environ.copy()
    env.update(
        {
            "DBUS_SESSION_BUS_ADDRESS": bus,
            "HOME": os.fspath(preview_home),
            "XDG_CONFIG_HOME": os.fspath(preview_config),
            "XDG_DATA_HOME": os.fspath(preview_data),
            "XDG_STATE_HOME": os.fspath(preview_state),
        }
    )
    for key in ("XDG_RUNTIME_DIR", "XDG_DATA_DIRS"):
        if shell_env.get(key):
            env[key] = shell_env[key]
    env.pop("BASH_ENV", None)
    env.pop("ENV", None)
    return env


def gsettings_get_theme(env: dict[str, str]) -> str:
    raw = run_checked(
        [
            "gsettings",
            "get",
            "org.gnome.shell.extensions.user-theme",
            "name",
        ],
        env=env,
    )
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        raise HotReloadError(f"unexpected User Themes setting value: {raw}") from exc
    if not isinstance(value, str):
        raise HotReloadError(f"unexpected User Themes setting value: {raw}")
    return value


def gsettings_set_theme(env: dict[str, str], theme: str) -> None:
    run_checked(
        [
            "gsettings",
            "set",
            "org.gnome.shell.extensions.user-theme",
            "name",
            repr(theme),
        ],
        env=env,
    )


def replace_live_theme(
    staged_theme: Path,
    live_theme: Path,
    *,
    env: dict[str, str],
    expected_theme: str,
    shell_pid: int,
    token: str,
) -> None:
    current_theme = gsettings_get_theme(env)
    if current_theme != expected_theme:
        raise HotReloadError(
            f"nested Shell uses theme {current_theme!r}, expected {expected_theme!r}"
        )

    backup = live_theme.parent / f".{live_theme.name}.hot-reload-backup"
    if backup.exists() or backup.is_symlink():
        if backup.is_dir() and not backup.is_symlink():
            shutil.rmtree(backup)
        else:
            backup.unlink()

    unloaded = False
    moved_old = False
    moved_new = False
    try:
        validate_shell(shell_pid, token)
        gsettings_set_theme(env, "")
        unloaded = True
        validate_shell(shell_pid, token)

        if live_theme.exists() or live_theme.is_symlink():
            os.replace(live_theme, backup)
            moved_old = True
        os.replace(staged_theme, live_theme)
        moved_new = True

        validate_shell(shell_pid, token)
        gsettings_set_theme(env, expected_theme)
        validate_shell(shell_pid, token)
    except Exception:
        if unloaded:
            try:
                gsettings_set_theme(env, "")
            except Exception:
                pass
        if moved_new and (live_theme.exists() or live_theme.is_symlink()):
            try:
                if live_theme.is_dir() and not live_theme.is_symlink():
                    shutil.rmtree(live_theme)
                else:
                    live_theme.unlink()
            except OSError:
                pass
        if moved_old and backup.exists():
            try:
                os.replace(backup, live_theme)
            except OSError:
                pass
        if unloaded:
            try:
                gsettings_set_theme(env, expected_theme)
            except Exception:
                pass
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and hot-reload the Fedora Nova theme in nested Shell Preview."
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--preview-home", required=True, type=Path)
    parser.add_argument("--preview-config", required=True, type=Path)
    parser.add_argument("--preview-data", required=True, type=Path)
    parser.add_argument("--preview-state", required=True, type=Path)
    parser.add_argument("--shell-pid", required=True, type=int)
    parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)

    staging_root: Path | None = None
    try:
        repo_root = require_dir(args.repo_root, "repo root")
        core = require_dir(repo_root / "core", "core")
        preview_home = require_dir(args.preview_home, "preview home")
        preview_config = require_dir(args.preview_config, "preview config")
        preview_data = require_dir(args.preview_data, "preview data")
        preview_state = require_dir(args.preview_state, "preview state")

        shell_env = validate_shell(args.shell_pid, args.token)
        staging_root, staged_theme = build_staged_theme(
            repo_root,
            core,
            args.profile,
            args.theme,
            preview_config,
            preview_state,
        )
        validate_shell(args.shell_pid, args.token)

        env = nested_gsettings_env(
            shell_env,
            preview_home,
            preview_config,
            preview_data,
            preview_state,
        )
        live_theme = preview_data / "themes" / args.theme
        replace_live_theme(
            staged_theme,
            live_theme,
            env=env,
            expected_theme=args.theme,
            shell_pid=args.shell_pid,
            token=args.token,
        )
        print(f"Theme hot reload applied: {args.theme}")
        return 0
    except (HotReloadError, OSError, ValueError) as exc:
        print(f"theme_hot_reload.py: {exc}", file=sys.stderr)
        return 2
    finally:
        if staging_root is not None and staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
