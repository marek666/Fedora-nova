from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .constants import CORE_ROOT

HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_hex(value: str) -> str:
    if not HEX_RE.fullmatch(value.strip()):
        raise ValueError(f"Neplatná HEX barva: {value}")
    return "#" + value.strip().lstrip("#").upper()


def slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    if not slug:
        raise ValueError("Název profilu nesmí být prázdný.")
    return slug[:48]


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def message(self) -> str:
        text = (self.stderr or self.stdout).strip()
        return text.splitlines()[-1] if text else "Hotovo."


class Backend:
    def __init__(self) -> None:
        self.config_home = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )
        self.nova_config = self.config_home / "fedora-nova"
        self.nova_config.mkdir(parents=True, exist_ok=True)

        self.in_flatpak = Path("/.flatpak-info").exists()
        preview_setting = os.environ.get("FEDORA_NOVA_PREVIEW")
        forced_preview = preview_setting == "1"
        forced_host = preview_setting == "0"
        self.host_allowed = (
            forced_host or os.environ.get("FEDORA_NOVA_HOST_ALLOWED") == "1"
        )
        self.runtime_mode = (
            "preview"
            if (forced_preview or not self.host_allowed or self.in_flatpak)
            else "host"
        )
        self.core_root = CORE_ROOT
        self.cli = self._resolve_cli()

    def _resolve_cli(self) -> Path | None:
        explicit = os.environ.get("FEDORA_NOVA_CLI")
        if explicit:
            path = Path(explicit)
            return path if path.is_file() else None

        bundled = self.core_root / "nova"
        if bundled.is_file():
            return bundled

        installed = shutil.which("fedora-nova")
        return Path(installed) if installed else None

    @property
    def preview(self) -> bool:
        return self.runtime_mode == "preview"

    @property
    def mode_label(self) -> str:
        if self.runtime_mode == "preview":
            return "Flatpak Preview" if self.in_flatpak else "Preview"
        return "System Host (Flatpak bridge)" if self.in_flatpak else "Native Host"

    @property
    def can_host(self) -> bool:
        if not self.host_allowed:
            return False
        if not self.in_flatpak:
            return self.cli is not None
        return shutil.which("flatpak-spawn") is not None

    def shell_preview_available(self) -> bool:
        if self.in_flatpak:
            result = self._host_shell(
                'test -x "$HOME/.local/bin/fedora-nova-shell-preview"'
            )
            return result.ok

        return (
            shutil.which("fedora-nova-shell-preview") is not None
            or (self.core_root.parent / "dev-shell-preview.sh").is_file()
        )

    def _shell_preview_helper(self) -> str | None:
        helper = shutil.which("fedora-nova-shell-preview")
        if helper is None:
            candidate = self.core_root.parent / "dev-shell-preview.sh"
            if candidate.is_file():
                helper = str(candidate)
        return helper

    @staticmethod
    def _preview_supervisor_matches(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return False
        markers = {"dev-shell-preview.sh", "fedora-nova-shell-preview"}
        for raw_arg in cmdline.split(b"\0"):
            if not raw_arg:
                continue
            try:
                arg = os.fsdecode(raw_arg)
            except UnicodeError:
                continue
            if Path(arg).name in markers:
                return True
        return False

    def shell_preview_running(self) -> bool:
        if self.in_flatpak:
            result = self._host_shell(
                'pidfile="${XDG_CACHE_HOME:-$HOME/.cache}/fedora-nova-shell-preview/runtime/supervisor.pid"; '
                '[ -s "$pidfile" ] || exit 1; '
                'pid="$(cat "$pidfile")"; '
                'case "$pid" in ""|*[!0-9]*) exit 1;; esac; '
                'kill -0 "$pid" 2>/dev/null || exit 1; '
                'tr "\\0" "\\n" < "/proc/$pid/cmdline" 2>/dev/null | '
                'grep -Eq "(^|/)(dev-shell-preview\\.sh|fedora-nova-shell-preview)$"'
            )
            return result.ok

        pidfile = (
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            / "fedora-nova-shell-preview/runtime/supervisor.pid"
        )
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        return self._preview_supervisor_matches(pid)

    def launch_shell_preview(self, profile: str, watch: bool = False) -> CommandResult:
        if watch and self.shell_preview_running():
            return CommandResult(
                2,
                stderr=(
                    "Live Shell Preview už běží. Zavři jeho okno nebo použij "
                    "Zastavit Live Preview."
                ),
            )

        if self.in_flatpak:
            return self._host_shell(
                'preview="$HOME/.local/bin/fedora-nova-shell-preview"; '
                '[ -x "$preview" ] || { '
                'echo "Host helper chybí. Spusť z projektu ./dev-setup-fedora.sh" >&2; '
                'exit 127; }; '
                'if [ "$2" = "1" ]; then set -- --watch "$1"; '
                'else set -- "$1"; fi; '
                'nohup "$preview" "$@" '
                '> "${XDG_CACHE_HOME:-$HOME/.cache}/fedora-nova-shell-preview-launch.log" '
                '2>&1 < /dev/null &',
                profile,
                "1" if watch else "0",
            )

        helper = self._shell_preview_helper()
        if helper is None:
            return CommandResult(
                127,
                stderr="Shell Preview helper chybí. Spusť ./dev-setup-fedora.sh.",
            )

        command = [helper]
        if watch:
            command.append("--watch")
        command.append(profile)

        try:
            subprocess.Popen(command)
        except OSError as exc:
            return CommandResult(126, stderr=str(exc))
        message = (
            "Live nested GNOME Shell Preview spuštěn."
            if watch
            else "Nested GNOME Shell Preview spuštěn."
        )
        return CommandResult(0, stdout=message)

    def stop_shell_preview(self) -> CommandResult:
        if self.in_flatpak:
            return self._host_shell(
                'preview="$HOME/.local/bin/fedora-nova-shell-preview"; '
                '[ -x "$preview" ] || { '
                'echo "Host helper chybí. Spusť z projektu ./dev-setup-fedora.sh" >&2; '
                'exit 127; }; '
                'exec "$preview" --stop'
            )

        helper = self._shell_preview_helper()
        if helper is None:
            return CommandResult(
                127,
                stderr="Shell Preview helper chybí. Spusť ./dev-setup-fedora.sh.",
            )

        try:
            proc = subprocess.run(
                [helper, "--stop"],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return CommandResult(126, stderr=str(exc))
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)

    def set_runtime_mode(self, mode: str) -> CommandResult:
        if mode not in {"preview", "host"}:
            return CommandResult(2, stderr=f"Neznámý backend: {mode}")
        if mode == "host" and not self.can_host:
            return CommandResult(
                127,
                stderr=(
                    "System Host není dostupný. Ve Flatpaku chybí flatpak-spawn "
                    "nebo na hostiteli není Fedora Nova CLI."
                ),
            )
        self.runtime_mode = mode
        return CommandResult(0, stdout=self.mode_label)

    def _host_spawn(self, argv: list[str]) -> CommandResult:
        if not self.in_flatpak:
            try:
                proc = subprocess.run(
                    argv,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError as exc:
                return CommandResult(126, stderr=str(exc))
            return CommandResult(proc.returncode, proc.stdout, proc.stderr)

        try:
            proc = subprocess.run(
                ["flatpak-spawn", "--host", *argv],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return CommandResult(126, stderr=str(exc))
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)

    def _host_shell(self, script: str, *args: str) -> CommandResult:
        return self._host_spawn(["sh", "-lc", script, "fedora-nova-host", *args])

    def _host_cli(self, *args: str) -> CommandResult:
        # Login shell is intentional so ~/.local/bin is available on Fedora.
        script = (
            'command -v fedora-nova >/dev/null 2>&1 || { '
            'echo "Fedora Nova CLI na hostiteli nebylo nalezeno." >&2; '
            "exit 127; }; exec fedora-nova \"$@\""
        )
        return self._host_shell(script, *args)

    def read_state(self, name: str, default: str) -> str:
        if self.runtime_mode == "host" and self.in_flatpak:
            result = self._host_shell(
                'base="${XDG_CONFIG_HOME:-$HOME/.config}/fedora-nova"; '
                'file="$base/$1"; '
                '[ -s "$file" ] && cat "$file" || true',
                name,
            )
            value = result.stdout.strip()
            return value or default

        path = self.nova_config / name
        try:
            value = path.read_text(encoding="utf-8").strip()
            return value or default
        except OSError:
            return default

    def write_state(self, name: str, value: str) -> None:
        if self.runtime_mode == "host" and self.in_flatpak:
            self._host_shell(
                'base="${XDG_CONFIG_HOME:-$HOME/.config}/fedora-nova"; '
                'mkdir -p "$base"; printf "%s\\n" "$2" > "$base/$1"',
                name,
                value,
            )
            return
        (self.nova_config / name).write_text(value.strip() + "\n", encoding="utf-8")

    def _profiles_path(self) -> Path:
        installed = self.core_root / "config/profiles.json"
        if installed.is_file():
            return installed
        return self.nova_config / "profiles.json"

    def profiles(self) -> list[tuple[str, str]]:
        # `system` is a pseudo-profile used to compare against stock GNOME.
        rows: list[tuple[str, str]] = [
            ("system", "Systémový GNOME — bez Fedora Nova Shell theme a docku")
        ]
        path = self._profiles_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rows.append(("tech", "Nova Tech — výchozí profil"))
            return rows

        for profile_id, item in data.get("profiles", {}).items():
            rows.append(
                (
                    profile_id,
                    f"{item.get('title', profile_id)} — "
                    f"{item.get('description', '')}",
                )
            )

        custom_dir = self.nova_config / "custom-profiles"
        if self.runtime_mode == "preview" and custom_dir.is_dir():
            for file in sorted(custom_dir.glob("*.json")):
                try:
                    item = json.loads(file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                profile_id = str(item.get("id", file.stem))
                rows.append(
                    (
                        profile_id,
                        f"{item.get('title', profile_id)} · Forge — "
                        f"{item.get('description', '')}",
                    )
                )
        return rows

    def curves(self) -> list[tuple[str, str]]:
        path = self.core_root / "config/curves.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [("squircle", "Continuous Squircle")]
        return [
            (
                key,
                f"{value.get('title', key)} — {value.get('description', '')}",
            )
            for key, value in data.get("presets", {}).items()
        ]

    def profile_data(self) -> dict[str, Any]:
        profile_id = self.read_state("current-profile", "tech")
        if profile_id == "system":
            return {
                "title": "System GNOME",
                "accent": "#3584E4",
                "secondary": "#9141AC",
                "panel": "#242424",
                "large": "#303030",
                "text": "#FFFFFF",
            }

        path = self._profiles_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles = data.get("profiles", {})
            if profile_id in profiles:
                return dict(profiles[profile_id])
            default_profile = str(data.get("default", "tech"))
            if default_profile in profiles:
                return dict(profiles[default_profile])
        except (OSError, json.JSONDecodeError):
            pass

        custom = self.nova_config / "custom-profiles" / f"{profile_id}.json"
        try:
            return json.loads(custom.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def monitor_enabled(self) -> bool:
        if self.preview:
            return self.read_state("preview-monitors", "off") == "on"
        result = self.run("monitors", "status")
        return (
            "Enabled:    yes" in result.stdout
            or "Enabled:    pending-or-enabled" in result.stdout
        )

    def run(self, *args: str) -> CommandResult:
        if self.preview:
            return self._run_preview(*args)

        # Pseudo-profile: use Fedora Nova safe mode and remember the comparison state.
        if len(args) >= 2 and args[0] == "profile" and args[1] == "system":
            result = self._host_cli("safe-mode") if self.in_flatpak else self._run_native("safe-mode")
            if result.ok:
                self.write_state("current-profile", "system")
            return result

        if self.in_flatpak:
            return self._host_cli(*args)
        return self._run_native(*args)

    def _run_native(self, *args: str) -> CommandResult:
        if self.cli is None:
            return CommandResult(
                127,
                stderr=(
                    "Fedora Nova CLI nebylo nalezeno. "
                    "Nainstaluj core nebo použij Preview režim."
                ),
            )

        env = os.environ.copy()
        env.setdefault("FEDORA_NOVA_APP_DIR", str(self.core_root))
        try:
            proc = subprocess.run(
                [str(self.cli), *args],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
        except OSError as exc:
            return CommandResult(126, stderr=str(exc))
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)

    def _run_preview(self, *args: str) -> CommandResult:
        if not args:
            return CommandResult(0, stdout="Preview: no command")

        command = args[0]
        value = args[1] if len(args) > 1 else ""

        state_map = {
            "profile": "current-profile",
            "curve": "current-curve",
            "hover": "current-hover",
            "icons": "current-icons",
            "gtk": "current-gtk",
        }
        if (
            command == "preset" and value in {"full", "nova-full", "mutter"}
        ) or command == "full-setup":
            profile_index = 2 if command == "preset" else 1
            profile = (
                args[profile_index]
                if len(args) > profile_index
                and not args[profile_index].startswith("--")
                else ""
            )
            if not profile or profile == "system":
                profile = self.read_state("current-profile", "tech")
                if profile == "system":
                    profile = "tech"
            self.write_state("current-profile", profile)
            self.write_state("current-dock", "balanced")
            self.write_state("current-motion", "balanced")
            self.write_state("current-curve", "squircle")
            self.write_state("current-hover", "circle")
            self.write_state("current-icons", "tela-steam")
            self.write_state("current-gtk", "on")
            self.write_state("preview-monitors", "on")
            self.write_state("preview-session-restore", "on")
            self.write_state("preview-welcome", "off")
            return CommandResult(
                0,
                stdout=(
                    "Preview: kompletní Nova setup je uložený "
                    "bez změn hostitelského systému."
                ),
            )
        if command == "session-restore" and value in {"enable", "on", "autostart"}:
            self.write_state("preview-session-restore", "on")
            return CommandResult(0, stdout="Preview: session restore zapnutý.")
        if command == "session-restore" and value in {"disable", "off"}:
            self.write_state("preview-session-restore", "off")
            return CommandResult(0, stdout="Preview: session restore vypnutý.")
        if command == "welcome" and value in {"off", "disable"}:
            self.write_state("preview-welcome", "off")
            return CommandResult(0, stdout="Preview: welcome dialog vypnutý.")
        if command == "welcome" and value == "status":
            state = self.read_state("preview-welcome", "unknown")
            return CommandResult(0, stdout=f"Preview: welcome dialog {state}.")
        if command in state_map and value:
            self.write_state(state_map[command], value)
        elif command == "monitors" and value in {"on", "off"}:
            self.write_state("preview-monitors", value)
        elif command == "forge" and len(args) >= 3:
            try:
                name = " ".join(args[1].split())
                primary = normalize_hex(args[2])
                secondary = (
                    normalize_hex(args[3]) if len(args) > 3 else "#2ED8E8"
                )
                profile_id = f"custom-{slugify(name)}"
            except ValueError as exc:
                return CommandResult(2, stderr=str(exc))
            profile = {
                "id": profile_id,
                "title": f"Nova {name[:80]}",
                "description": f"Preview Forge profil {primary}",
                "theme": "Fedora-Nova-Tech",
                "accent_name": "purple",
                "wallpaper": "fedora-nova-flow.svg",
                "dock_icon_size": 42,
                "dock_opacity": 0.8,
                "dock_color": "#09081B",
                "accent": primary,
                "secondary": secondary,
                "panel": "#09081B",
                "large": "#120C25",
                "text": "#F8EFFF",
            }
            custom_dir = self.nova_config / "custom-profiles"
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / f"{profile_id}.json").write_text(
                json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.write_state("current-profile", profile_id)

        return CommandResult(0, stdout=f"Preview mode: {' '.join(args)}")
