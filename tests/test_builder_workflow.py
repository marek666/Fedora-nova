"""Builder boundaries; backend calls never modify the host GNOME session."""
import json
import os
import runpy
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app/src"))
from fedora_nova import backend as backend_module

DEVEL_ID = "io.github.fedoranova.FedoraNova.Devel"
PRODUCTION_ID = "io.github.fedoranova.FedoraNova"


class BackendBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nova-builder-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.env = {
            "HOME": self.tmp.name,
            "XDG_CONFIG_HOME": self.tmp.name,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        self.enterContext(patch.dict(os.environ, self.env, clear=True))
        self.enterContext(patch.object(backend_module, "CORE_ROOT", REPO / "core"))

    def test_identity_defaults_and_explicit_native_host(self):
        for requested, preview, allowed, expected in [
            (None, None, None, DEVEL_ID),
            (None, "0", "1", DEVEL_ID),
            (DEVEL_ID, "0", "1", DEVEL_ID),
            ("invalid.application", "0", "1", DEVEL_ID),
            (PRODUCTION_ID, None, None, DEVEL_ID),
            (PRODUCTION_ID, "0", None, DEVEL_ID),
            (PRODUCTION_ID, "0", "0", DEVEL_ID),
            (PRODUCTION_ID, "1", "1", DEVEL_ID),
            (PRODUCTION_ID, "0", "1", PRODUCTION_ID),
        ]:
            with self.subTest(requested=requested, preview=preview, allowed=allowed):
                env = dict(self.env)
                for key, value in [("FEDORA_NOVA_APP_ID", requested),
                                   ("FEDORA_NOVA_PREVIEW", preview),
                                   ("FEDORA_NOVA_HOST_ALLOWED", allowed)]:
                    if value is not None:
                        env[key] = value
                with patch.dict(os.environ, env, clear=True):
                    constants = runpy.run_path(str(REPO / "app/src/fedora_nova/constants.py"))
                    self.assertEqual(constants["APP_ID"], expected)

    def test_native_host_needs_both_explicit_flags(self):
        for preview, allowed, expected in [
            (None, None, False), (None, "1", False),
            ("0", None, False), ("0", "0", False),
            ("1", "1", False), ("0", "1", True),
        ]:
            with self.subTest(preview=preview, allowed=allowed):
                env = dict(self.env)
                if preview is not None:
                    env["FEDORA_NOVA_PREVIEW"] = preview
                if allowed is not None:
                    env["FEDORA_NOVA_HOST_ALLOWED"] = allowed
                with patch.dict(os.environ, env, clear=True):
                    backend = backend_module.Backend()
                    self.assertEqual(backend.host_allowed, expected)
                    self.assertEqual(backend.can_host, expected)
                    self.assertEqual(backend.runtime_mode, "host" if expected else "preview")
                    self.assertEqual(backend.set_runtime_mode("host").ok, expected)

    def test_flatpak_rejects_modes_and_all_host_entrypoints(self):
        exists = Path.exists
        for preview, allowed in [(None, None), ("1", "1"), ("0", None), ("0", "1")]:
            with self.subTest(preview=preview, allowed=allowed):
                env = dict(self.env)
                if preview is not None:
                    env["FEDORA_NOVA_PREVIEW"] = preview
                if allowed is not None:
                    env["FEDORA_NOVA_HOST_ALLOWED"] = allowed
                with patch.dict(os.environ, env, clear=True), patch.object(
                    Path, "exists", lambda p: str(p) == "/.flatpak-info" or exists(p)
                ), patch.object(backend_module.subprocess, "run") as run, patch.object(
                    backend_module.subprocess, "Popen"
                ) as popen:
                    os.environ["FEDORA_NOVA_APP_ID"] = PRODUCTION_ID
                    constants = runpy.run_path(str(REPO / "app/src/fedora_nova/constants.py"))
                    self.assertEqual(constants["APP_ID"], DEVEL_ID)
                    backend = backend_module.Backend()
                    self.assertEqual(backend.runtime_mode, "preview")
                    self.assertFalse(backend.host_allowed)
                    self.assertFalse(backend.can_host)
                    self.assertFalse(backend.set_runtime_mode("host").ok)
                    self.assertFalse(backend.shell_preview_available())
                    self.assertFalse(backend.shell_preview_running())
                    self.assertIsNone(backend._shell_preview_helper())
                    for result in [
                        backend._host_spawn(["/usr/bin/true"]),
                        backend._host_shell("true"),
                        backend._host_cli("status"),
                        backend._run_native("status"),
                        backend.launch_shell_preview("tech"),
                        backend.launch_shell_preview("tech", watch=True),
                        backend.stop_shell_preview(),
                    ]:
                        self.assertFalse(result.ok)
                    self.assertTrue(backend.run("profile", "tech").ok)
                    run.assert_not_called()
                    popen.assert_not_called()
                    self.assertEqual(backend.runtime_mode, "preview")

    def test_explicit_helper_never_falls_back_when_missing_or_not_executable(self):
        helper = Path(self.tmp.name) / "checkout with spaces" / "dev-shell-preview.sh"
        helper.parent.mkdir()
        os.environ["FEDORA_NOVA_SHELL_PREVIEW"] = str(helper)
        backend = backend_module.Backend()
        with patch.object(backend_module.shutil, "which", return_value="/stale/helper") as which:
            self.assertIsNone(backend._shell_preview_helper())
            helper.write_text("#!/bin/sh\nexit 0\n")
            helper.chmod(0o644)
            self.assertFalse(backend.shell_preview_available())
            helper.chmod(0o755)
            self.assertEqual(backend._shell_preview_helper(), str(helper))
            with patch.object(backend_module.subprocess, "Popen") as popen:
                self.assertTrue(backend.launch_shell_preview("tech").ok)
                popen.assert_called_once_with([str(helper), "tech"])
            which.assert_not_called()

    def test_checkout_helper_precedes_global_helper(self):
        backend = backend_module.Backend()
        with patch.object(backend_module.shutil, "which", return_value="/stale/helper"):
            self.assertEqual(backend._shell_preview_helper(), str(REPO / "dev-shell-preview.sh"))

    def test_explicit_missing_cli_does_not_fall_back(self):
        os.environ["FEDORA_NOVA_CLI"] = str(Path(self.tmp.name) / "missing-cli")
        with patch.object(backend_module.shutil, "which", return_value="/stale/cli") as which:
            self.assertIsNone(backend_module.Backend().cli)
            which.assert_not_called()


class InstalledLaunchers(unittest.TestCase):
    def test_installed_launchers_override_stale_environment(self):
        # Execute configured templates against an installed-layout fixture. Only
        # the UI entrypoint is replaced; constants and Backend are real modules.
        with tempfile.TemporaryDirectory(prefix="nova-installed-") as tmp:
            root = Path(tmp)
            pkg = root / "installed share" / "fedora-nova"
            shutil.copytree(REPO / "app/src/fedora_nova", pkg / "fedora_nova",
                            ignore=shutil.ignore_patterns("__pycache__"))
            core = pkg / "core"
            core.mkdir()
            (core / "nova").write_text("#!/bin/sh\nexit 99\n")
            (core / "nova").chmod(0o755)
            stale = root / "stale-bin"
            stale.mkdir()
            for name in ["fedora-nova", "fedora-nova-shell-preview"]:
                (stale / name).write_text("#!/bin/sh\nexit 99\n")
                (stale / name).chmod(0o755)
            # A leftover helper next to installed core must also be ignored.
            shutil.copy2(stale / "fedora-nova-shell-preview", pkg / "dev-shell-preview.sh")
            (pkg / "fedora_nova/application.py").write_text('''
import json, os
from pathlib import Path
from unittest.mock import patch

def main():
    exists = Path.exists
    with patch.object(Path, "exists", lambda p: (
        str(p) == "/.flatpak-info" and os.environ["NOVA_TEST_FLATPAK"] == "1"
    ) or (str(p) != "/.flatpak-info" and exists(p))):
        from .constants import APP_ID, PROJECT_ROOT, CORE_ROOT
        from .backend import Backend
        backend = Backend()
        with patch("subprocess.run") as run, patch("subprocess.Popen") as popen:
            helper = backend._shell_preview_helper()
            if backend.in_flatpak:
                assert not backend._host_spawn(["/usr/bin/true"]).ok
                assert not backend._run_native("status").ok
                assert not backend.set_runtime_mode("host").ok
            run.assert_not_called()
            popen.assert_not_called()
        print(json.dumps(dict(
            app_id=APP_ID, project=str(PROJECT_ROOT), core=str(CORE_ROOT),
            cli=str(backend.cli), mode=backend.runtime_mode,
            allowed=backend.host_allowed, can_host=backend.can_host,
            helper=helper, env={k: v for k, v in os.environ.items()
                               if k.startswith("FEDORA_NOVA_")},
        )))
    return 0
''')
            for command, identity, preview, allowed in [
                ("fedora-nova-settings", PRODUCTION_ID, "0", "1"),
                ("fedora-nova-settings-devel", DEVEL_ID, "1", "0"),
            ]:
                launcher = root / command
                template = (REPO / "app/src" / (command + ".in")).read_text()
                launcher.write_text(template.replace("@PYTHON@", sys.executable)
                                    .replace("@PKGDATADIR@", str(pkg)))
                for flatpak in [False, True]:
                    with self.subTest(command=command, flatpak=flatpak):
                        env = {
                            "HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
                            "PATH": str(stale) + ":/usr/bin:/bin",
                            "FEDORA_NOVA_PROJECT_ROOT": "/stale/worktree",
                            "FEDORA_NOVA_CORE": "/stale/worktree/core",
                            "FEDORA_NOVA_APP_DIR": "/stale/worktree/core",
                            "FEDORA_NOVA_CLI": str(stale / "fedora-nova"),
                            "FEDORA_NOVA_SHELL_PREVIEW": str(stale / "fedora-nova-shell-preview"),
                            "FEDORA_NOVA_DEV_NON_UNIQUE": "1",
                            "FEDORA_NOVA_APP_ID": DEVEL_ID if identity == PRODUCTION_ID else PRODUCTION_ID,
                            "FEDORA_NOVA_PREVIEW": "1" if preview == "0" else "0",
                            "FEDORA_NOVA_HOST_ALLOWED": "0" if allowed == "1" else "1",
                            "NOVA_TEST_FLATPAK": "1" if flatpak else "0",
                        }
                        result = subprocess.run([sys.executable, str(launcher)], env=env,
                                                capture_output=True, text=True, check=True)
                        data = json.loads(result.stdout)
                        host = identity == PRODUCTION_ID and not flatpak
                        self.assertEqual(data["app_id"], DEVEL_ID if flatpak else identity)
                        self.assertEqual(data["mode"], "host" if host else "preview")
                        self.assertEqual(data["allowed"], host)
                        self.assertEqual(data["can_host"], host)
                        self.assertEqual(data["project"], str(pkg))
                        self.assertEqual(data["core"], str(core))
                        self.assertEqual(data["cli"], str(core / "nova"))
                        self.assertEqual(data["env"]["FEDORA_NOVA_APP_DIR"], str(core))
                        self.assertEqual(data["env"]["FEDORA_NOVA_APP_ID"], identity)
                        self.assertEqual(data["env"]["FEDORA_NOVA_PREVIEW"], preview)
                        self.assertEqual(data["env"]["FEDORA_NOVA_HOST_ALLOWED"], allowed)
                        self.assertNotIn("FEDORA_NOVA_DEV_NON_UNIQUE", data["env"])
                        self.assertIsNone(data["helper"])

    def test_desktop_identities_and_flatpak_entrypoint(self):
        import configparser
        import xml.etree.ElementTree as ET

        for identity, command in [(PRODUCTION_ID, "fedora-nova-settings"),
                                  (DEVEL_ID, "fedora-nova-settings-devel")]:
            with self.subTest(identity=identity):
                desktop = configparser.ConfigParser(interpolation=None)
                desktop.read(REPO / "app/data" / (identity + ".desktop.in"))
                self.assertEqual(desktop["Desktop Entry"]["Exec"], command)
                self.assertEqual(desktop["Desktop Entry"]["Icon"], identity)
                ET.parse(REPO / "app/data" / (identity + ".svg"))
        manifest = json.loads((REPO / (DEVEL_ID + ".json")).read_text())
        self.assertEqual(manifest["app-id"], DEVEL_ID)
        self.assertEqual(manifest["command"], "fedora-nova-settings-devel")
        module = next(m for m in manifest["modules"] if m["name"] == "fedora-nova")
        self.assertIn("-Dproduction_app=false", module["config-opts"])
        self.assertIn("--env=FEDORA_NOVA_PREVIEW=1", manifest["finish-args"])
        self.assertNotIn("--talk-name=org.freedesktop.Flatpak", manifest["finish-args"])


    @unittest.skipUnless(shutil.which("meson"), "Meson is required for packaging tests")
    def test_meson_production_packaging_boundary(self):
        with tempfile.TemporaryDirectory(prefix="nova-packaging-") as tmp:
            for production in [True, False]:
                with self.subTest(production=production):
                    build = Path(tmp) / ("production" if production else "devel")
                    stage = build / "staging"
                    setup = ["meson", "setup", str(build), str(REPO), "--prefix=/app"]
                    # The default must include production; Flatpak opts out.
                    if not production:
                        setup.append("-Dproduction_app=false")
                    for command in [setup, ["meson", "compile", "-C", str(build)],
                                    ["meson", "install", "-C", str(build),
                                     "--destdir", str(stage)]]:
                        result = subprocess.run(command, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    for identity, launcher, expected in [
                        (DEVEL_ID, "fedora-nova-settings-devel", True),
                        (PRODUCTION_ID, "fedora-nova-settings", production),
                    ]:
                        for relative in [
                            "bin/" + launcher,
                            "share/applications/" + identity + ".desktop",
                            "share/icons/hicolor/scalable/apps/" + identity + ".svg",
                            "share/glib-2.0/schemas/" + identity + ".gschema.xml",
                        ]:
                            path = stage / "app" / relative
                            self.assertEqual(path.is_file(), expected, str(path))
                        if expected:
                            self.assertTrue(os.access(stage / "app/bin" / launcher, os.X_OK))


# Executed in place of the launcher's final python3 invocation. It imports the
# actual application, suppresses only display styling, and registers it on the
# private test bus. No window is created and no runtime CLI is executed.
APPLICATION_PROBE = '''#!/usr/bin/python3
import json, os
from unittest.mock import patch
from gi.repository import Gio, GLib
from fedora_nova.application import NovaApplication
from fedora_nova.backend import Backend
from fedora_nova.constants import PROJECT_ROOT, CORE_ROOT, DEVEL_APP_ID, PRODUCTION_APP_ID
from fedora_nova.state import WindowState
with patch.object(NovaApplication, "_configure_style"), patch.object(NovaApplication, "_load_css"):
    app = NovaApplication()
app.register(None)
backend = Backend()
window_state = WindowState()
schemas = {}
for identity in [DEVEL_APP_ID, PRODUCTION_APP_ID]:
    schema = Gio.SettingsSchemaSource.get_default().lookup(identity, True)
    schemas[identity] = dict(path=schema.get_path(), keys={
        key: [schema.get_key(key).get_value_type().dup_string(),
              schema.get_key(key).get_default_value().unpack()]
        for key in schema.list_keys()
    })
# Use the fixture's memory backend to verify the two schema paths are independent.
devel_state = Gio.Settings.new(DEVEL_APP_ID)
host_state = Gio.Settings.new(PRODUCTION_APP_ID)
devel_state.set_int("window-width", 480)
host_state.set_int("window-width", 1200)
assert devel_state.get_int("window-width") == 480
assert host_state.get_int("window-width") == 1200
print(json.dumps(dict(remote=app.get_is_remote(), flags=int(app.get_flags()),
    app_id=app.get_application_id(), requested_id=os.environ.get("FEDORA_NOVA_APP_ID"),
    schema_id=window_state.settings.props.schema_id,
    schema_path=window_state.settings.props.path, schemas=schemas,
    mode=backend.runtime_mode, allowed=backend.host_allowed, can_host=backend.can_host,
    project=str(PROJECT_ROOT), core=str(CORE_ROOT), cli=str(backend.cli),
    config=str(backend.nova_config),
    helper=backend._shell_preview_helper(), app_dir=os.environ.get("FEDORA_NOVA_APP_DIR"),
    pythonpath=os.environ.get("PYTHONPATH"), marker=os.environ.get("FEDORA_NOVA_DEV_NON_UNIQUE"))), flush=True)
loop = GLib.MainLoop()
def stop_if_requested(*args):
    loop.quit()
    return False
GLib.io_add_watch(0, GLib.IO_IN | GLib.IO_HUP, stop_if_requested)
loop.run()
'''


class NativeLaunchers(unittest.TestCase):
    def test_preview_state_is_isolated_and_host_config_is_preserved(self):
        for custom_config in [False, True]:
            with self.subTest(custom_config=custom_config), tempfile.TemporaryDirectory(
                prefix="nova-builder-config-"
            ) as tmp:
                root = Path(tmp)
                checkout = root / "checkout with spaces"
                checkout.mkdir()
                shutil.copy2(REPO / "dev-run.sh", checkout / "dev-run.sh")
                for name in ["app", "core"]:
                    (checkout / name).symlink_to(REPO / name, target_is_directory=True)
                home = root / "home"
                host_config = root / "custom-config" if custom_config else home / ".config"
                host_state = host_config / "fedora-nova/current-profile"
                host_state.parent.mkdir(parents=True)
                host_state.write_text("host-profile\n")
                # Even with a custom XDG path, the default host config is untouched.
                default_state = home / ".config/fedora-nova/current-profile"
                default_state.parent.mkdir(parents=True, exist_ok=True)
                default_state.write_text("host-profile\n")
                binary = root / "bin"
                binary.mkdir()
                observer = binary / "python3"
                observer.write_text("""#!/usr/bin/python3
import json
from fedora_nova.backend import Backend
backend = Backend()
before = backend.read_state("current-profile", "unset")
if backend.preview:
    backend.write_state("current-profile", "preview-profile")
print(json.dumps(dict(config=str(backend.nova_config), before=before,
                      after=backend.read_state("current-profile", "unset"))))
""")
                observer.chmod(0o755)
                env = {k: v for k, v in os.environ.items()
                       if not k.startswith(("FEDORA_NOVA_", "XDG_"))}
                env.update(HOME=str(home), PATH=str(binary) + ":" + os.environ["PATH"],
                           PYTHONDONTWRITEBYTECODE="1")
                if custom_config:
                    env["XDG_CONFIG_HOME"] = str(host_config)
                for mode in ["preview", "host"]:
                    result = subprocess.run([str(checkout / "dev-run.sh"), mode],
                                            env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    data = json.loads(result.stdout)
                    expected = (checkout / ".dev-build/preview-config/fedora-nova"
                                if mode == "preview" else host_config / "fedora-nova")
                    self.assertEqual(data["config"], str(expected))
                    self.assertEqual(data["before"], "unset" if mode == "preview" else "host-profile")
                    self.assertEqual(data["after"], "preview-profile" if mode == "preview" else "host-profile")
                    self.assertEqual(host_state.read_text(), "host-profile\n")
                    self.assertEqual(default_state.read_text(), "host-profile\n")
                preview_state = checkout / ".dev-build/preview-config/fedora-nova/current-profile"
                self.assertEqual(preview_state.read_text(), "preview-profile\n")

    def test_non_unique_is_native_development_only(self):
        from gi.repository import Gio
        from fedora_nova.application import NovaApplication

        exists = os.path.exists
        for marker, flatpak, non_unique in [(None, False, False), ("1", False, True),
                                            (None, True, False), ("1", True, False)]:
            with self.subTest(marker=marker, flatpak=flatpak), patch.dict(os.environ):
                os.environ.pop("FEDORA_NOVA_DEV_NON_UNIQUE", None)
                if marker is not None:
                    os.environ["FEDORA_NOVA_DEV_NON_UNIQUE"] = marker
                with patch("os.path.exists", side_effect=lambda p: flatpak if p == "/.flatpak-info" else exists(p)), patch.object(
                    NovaApplication, "_configure_style"
                ), patch.object(NovaApplication, "_load_css"):
                    app = NovaApplication()
                    self.assertEqual(bool(app.get_flags() & Gio.ApplicationFlags.NON_UNIQUE), non_unique)


    def test_poisoned_environment_and_two_independent_native_instances(self):
        if os.environ.get("NOVA_BUILDER_PRIVATE_BUS") != "1":
            if not shutil.which("dbus-run-session"):
                self.skipTest("dbus-run-session unavailable")
            env = {**os.environ, "NOVA_BUILDER_PRIVATE_BUS": "1"}
            result = subprocess.run(
                ["dbus-run-session", "--", sys.executable, "-B", "-m", "unittest", "-v",
                 "tests.test_builder_workflow.NativeLaunchers.test_poisoned_environment_and_two_independent_native_instances"],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        with tempfile.TemporaryDirectory(prefix="nova-builder-native-") as tmp:
            root = Path(tmp)
            binary = root / "bin"
            binary.mkdir()
            observer = binary / "python3"
            observer.write_text(APPLICATION_PROBE)
            observer.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("FEDORA_NOVA_", "XDG_"))}
            env.update(HOME=tmp, XDG_CONFIG_HOME=str(root / "config"),
                       XDG_DATA_HOME=str(root / "data"), XDG_STATE_HOME=str(root / "state"),
                       XDG_CACHE_HOME=str(root / "cache"), GSETTINGS_BACKEND="memory",
                       PATH=str(binary) + ":" + os.environ["PATH"], PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH="/stale/python", FEDORA_NOVA_PROJECT_ROOT="/stale/repo",
                       FEDORA_NOVA_CORE="/stale/core",
                       FEDORA_NOVA_CLI=str(Path.home() / ".local/bin/fedora-nova"),
                       FEDORA_NOVA_APP_DIR=str(Path.home() / ".local/share/fedora-nova"),
                       FEDORA_NOVA_HOST_ALLOWED="1",
                       FEDORA_NOVA_APP_ID="stale.application.Identity",
                       FEDORA_NOVA_SHELL_PREVIEW="/stale/dev-shell-preview.sh")
            processes = []
            try:
                for mode in ["preview", "host"]:
                    env["FEDORA_NOVA_APP_ID"] = PRODUCTION_ID if mode == "preview" else DEVEL_ID
                    process = subprocess.Popen([str(REPO / "dev-run.sh"), mode], env=env,
                                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True)
                    processes.append(process)
                    self.assertTrue(select.select([process.stdout], [], [], 10)[0], "application probe timed out")
                    line = process.stdout.readline()
                    if not line:
                        self.fail(process.communicate(timeout=5)[1])
                    result = json.loads(line)
                    self.assertFalse(result["remote"])
                    self.assertEqual(result["mode"], mode)
                    expected_id = DEVEL_ID if mode == "preview" else PRODUCTION_ID
                    self.assertEqual(result["app_id"], expected_id)
                    self.assertEqual(result["requested_id"], expected_id)
                    self.assertEqual(result["schema_id"], expected_id)
                    schema_path = "/io/github/fedoranova/FedoraNova/"
                    if mode == "preview":
                        schema_path += "Devel/"
                    self.assertEqual(result["schema_path"], schema_path)
                    schemas = result["schemas"]
                    self.assertEqual(schemas[DEVEL_ID]["path"], "/io/github/fedoranova/FedoraNova/Devel/")
                    self.assertEqual(schemas[PRODUCTION_ID]["path"], "/io/github/fedoranova/FedoraNova/")
                    self.assertEqual(schemas[PRODUCTION_ID]["keys"], schemas[DEVEL_ID]["keys"])
                    self.assertEqual(set(schemas[PRODUCTION_ID]["keys"]), {
                        "window-width", "window-height", "window-maximized", "last-page",
                    })
                    expected_config = (REPO / ".dev-build/preview-config/fedora-nova"
                                       if mode == "preview" else root / "config/fedora-nova")
                    self.assertEqual(result["config"], str(expected_config))
                    self.assertEqual(result["allowed"], mode == "host")
                    self.assertEqual(result["can_host"], mode == "host")
                    self.assertEqual(result["project"], str(REPO))
                    self.assertEqual(result["core"], str(REPO / "core"))
                    self.assertEqual(result["cli"], str(REPO / "core/nova"))
                    self.assertEqual(result["app_dir"], str(REPO / "core"))
                    self.assertEqual(result["helper"], str(REPO / "dev-shell-preview.sh"))
                    self.assertEqual(result["pythonpath"], str(REPO / "app/src"))
                    self.assertEqual(result["marker"], "1")
                self.assertTrue(all(p.poll() is None for p in processes))
            finally:
                for process in processes:
                    try:
                        process.communicate(input="stop\n", timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()


if __name__ == "__main__":
    unittest.main()
