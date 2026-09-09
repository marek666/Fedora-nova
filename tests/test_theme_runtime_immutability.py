"""Curve/hover may edit only isolated, writable user theme copies."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
THEME = "Fedora-Nova-Tech"
CSS = Path(THEME) / "gnome-shell/gnome-shell.css"


class ThemeRuntimeImmutability(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nova-theme-runtime-")
        self.root = Path(tmp.name)
        self.addCleanup(self.cleanup, tmp)
        self.core = self.root / "prefix/share/fedora-nova/core"
        for name in ["lib.sh", "apply-curve.sh", "apply-hover.sh", "curve_style.py",
                     "hover_style.py", "theme_runtime.py"]:
            target = self.core / "scripts" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / "core/scripts" / name, target)
        (self.core / "config").mkdir()
        profiles = json.loads((REPO / "core/config/profiles.json").read_text())
        self.profile = profiles["profiles"]["tech"]
        (self.core / "config/profiles.json").write_text(json.dumps({"profiles": {"tech": self.profile}}))
        shutil.copy2(REPO / "core/config/curves.json", self.core / "config/curves.json")
        self.source = self.core / "themes"
        self.put(self.source / CSS, "/* bundled sentinel */\nstage { color: red; }\n")
        self.put(self.source / THEME / "assets/source.txt", "bundled asset\n")
        self.data = self.root / "user data"
        self.runtime = self.data / "themes"
        self.config = self.root / "user config/fedora-nova"
        for name, value in {"current-curve": "squircle", "previous-curve": "old-curve",
                            "current-hover": "circle", "previous-hover": "old-hover"}.items():
            self.put(self.config / name, value + "\n")
        binary = self.root / "bin"
        for name in ["gsettings", "gnome-extensions"]:
            self.put(binary / name, "#!/bin/sh\nexit 1\n", executable=True)
        self.log = self.root / "python-args.jsonl"
        self.put(binary / "python3", f'''#!{sys.executable}
import json, os, sys
with open(os.environ["NOVA_TEST_ARGS"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
is_renderer = (os.path.basename(sys.argv[1]) == "hover_style.py" or
               (os.path.basename(sys.argv[1]) == "curve_style.py" and sys.argv[2] == "apply"))
if is_renderer and os.environ.get("NOVA_TEST_RENDER_FAILURE"):
    print("injected renderer failure", file=sys.stderr)
    sys.exit(77)
if is_renderer and os.environ.get("NOVA_TEST_SWAP_TARGET"):
    target = os.environ["NOVA_TEST_SWAP_TARGET"]
    os.unlink(target)
    if os.environ["NOVA_TEST_LINK"] == "symlink":
        os.symlink(os.environ["NOVA_TEST_SOURCE"], target)
    else:
        os.link(os.environ["NOVA_TEST_SOURCE"], target)
os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
''', executable=True)
        self.env = {"HOME": str(self.root / "home"), "XDG_DATA_HOME": str(self.data),
                    "XDG_CONFIG_HOME": str(self.config.parent),
                    "XDG_STATE_HOME": str(self.root / "state"),
                    "FEDORA_NOVA_APP_DIR": str(self.core), "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": str(binary) + os.pathsep + os.defpath,
                    "NOVA_TEST_ARGS": str(self.log)}

    def cleanup(self, tmp):
        # Only fixture permissions are restored; never follow links to repo data.
        for path in [self.root, *self.root.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        tmp.cleanup()

    def put(self, path, text, executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)
        return path

    def snapshot(self, root):
        return {str(p.relative_to(root)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in root.rglob("*") if p.is_file()}

    def states(self):
        return {p.name: p.read_bytes() for p in self.config.glob("*-curve")} | {
            p.name: p.read_bytes() for p in self.config.glob("*-hover")}

    def apply(self, kind, success=True, env=None):
        selected = "classic" if kind == "curve" else "tile"
        before = self.states()
        source = self.snapshot(self.source)
        result = subprocess.run([str(self.core / "scripts" / f"apply-{kind}.sh"), selected],
                                env=env or self.env, cwd=self.root, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((self.config / f"current-{kind}").read_text(), selected + "\n")
            if before[f"current-{kind}"] != (selected + "\n").encode():
                self.assertEqual((self.config / f"previous-{kind}").read_bytes(), before[f"current-{kind}"])
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stderr.strip())
            self.assertEqual(self.states(), before)
        self.assertEqual(self.snapshot(self.source), source)
        return result

    def test_missing_copies_created_for_curve_and_hover(self):
        for kind in ["curve", "hover"]:
            with self.subTest(kind=kind):
                if self.runtime.exists():
                    shutil.rmtree(self.runtime)
                self.apply(kind)
                text = (self.runtime / CSS).read_text()
                self.assertIn(f"/* NOVA_{kind.upper()}_START */", text)
                self.assertIn("bundled sentinel", text)
                self.assertEqual((self.runtime / THEME / "assets/source.txt").read_text(), "bundled asset\n")

    def test_read_only_source_produces_writable_copies(self):
        for path in [self.source, *self.source.rglob("*")]:
            path.chmod(0o555 if path.is_dir() else 0o444)
        for kind in ["curve", "hover"]:
            with self.subTest(kind=kind):
                self.apply(kind)
                self.assertTrue((self.runtime / CSS).stat().st_mode & stat.S_IWUSR)
        self.assertFalse((self.source / CSS).stat().st_mode & stat.S_IWUSR)

    def test_existing_user_and_custom_themes_are_preserved(self):
        self.put(self.runtime / CSS, "/* user sentinel */\nstage {}\n")
        self.put(self.runtime / THEME / "assets/source.txt", "user asset\n")
        custom = "Fedora-Nova-Custom-example"
        custom_css = self.put(self.runtime / custom / "gnome-shell/gnome-shell.css", "/* forge sentinel */\n")
        self.put(self.config / "custom-profiles/custom-example.json", json.dumps(dict(self.profile, theme=custom)))
        for kind in ["curve", "hover"]:
            self.apply(kind)
            self.assertIn("user sentinel", (self.runtime / CSS).read_text())
            self.assertNotIn("bundled sentinel", (self.runtime / CSS).read_text())
            self.assertIn("forge sentinel", custom_css.read_text())
            self.assertIn(f"/* NOVA_{kind.upper()}_START */", custom_css.read_text())
        self.assertEqual((self.runtime / THEME / "assets/source.txt").read_text(), "user asset\n")

    def test_actual_checkout_source_stays_unchanged(self):
        bundled = REPO / "core/themes"
        before = self.snapshot(bundled)
        env = dict(self.env, FEDORA_NOVA_APP_DIR=str(REPO / "core"))
        for kind in ["curve", "hover"]:
            self.apply(kind, env=env)
        self.assertEqual(self.snapshot(bundled), before)

    def test_missing_source_and_user_copy_preserves_state(self):
        shutil.rmtree(self.source)
        for kind in ["curve", "hover"]:
            self.assertIn("Chybí bundled theme", self.apply(kind, success=False).stderr)

    def test_existing_user_copy_needs_no_source_copy(self):
        self.put(self.runtime / CSS, "/* user sentinel */\n")
        shutil.rmtree(self.source)
        for kind in ["curve", "hover"]:
            self.apply(kind)

    @unittest.skipIf(os.geteuid() == 0, "Permission checks require an unprivileged user")
    def test_unwritable_user_file_preserves_all_state(self):
        css = self.put(self.runtime / CSS, "/* user sentinel */\n")
        css.chmod(0o444)
        for kind in ["curve", "hover"]:
            self.apply(kind, success=False)
        self.assertEqual(css.read_text(), "/* user sentinel */\n")

    @unittest.skipIf(os.geteuid() == 0, "Permission checks require an unprivileged user")
    def test_unwritable_runtime_directory_preserves_state(self):
        self.runtime.mkdir(parents=True)
        self.runtime.chmod(0o555)
        for kind in ["curve", "hover"]:
            self.apply(kind, success=False)

    def test_linked_runtime_targets_cannot_modify_source(self):
        for link_kind in ["root", "theme", "shell", "css", "hardlink"]:
            with self.subTest(link=link_kind):
                if self.runtime.is_symlink():
                    self.runtime.unlink()
                elif self.runtime.exists():
                    shutil.rmtree(self.runtime)
                if link_kind == "root":
                    self.runtime.parent.mkdir(parents=True, exist_ok=True)
                    self.runtime.symlink_to(self.source, target_is_directory=True)
                elif link_kind == "theme":
                    self.runtime.mkdir()
                    (self.runtime / THEME).symlink_to(self.source / THEME, target_is_directory=True)
                elif link_kind == "shell":
                    (self.runtime / THEME).mkdir(parents=True)
                    (self.runtime / THEME / "gnome-shell").symlink_to(self.source / THEME / "gnome-shell", target_is_directory=True)
                else:
                    (self.runtime / CSS).parent.mkdir(parents=True)
                    if link_kind == "css":
                        (self.runtime / CSS).symlink_to(self.source / CSS)
                    else:
                        os.link(self.source / CSS, self.runtime / CSS)
                for kind in ["curve", "hover"]:
                    self.apply(kind, success=False)

    def test_runtime_root_equal_to_bundled_root_is_rejected(self):
        env = dict(self.env, XDG_DATA_HOME=str(self.core))
        for kind in ["curve", "hover"]:
            self.apply(kind, success=False, env=env)

    def test_renderer_failure_does_not_update_history(self):
        for kind in ["curve", "hover"]:
            self.apply(kind, success=False, env=dict(self.env, NOVA_TEST_RENDER_FAILURE="1"))

    def test_links_introduced_after_preflight_are_rejected_by_renderer(self):
        for link in ["symlink", "hardlink"]:
            for kind in ["curve", "hover"]:
                with self.subTest(link=link, kind=kind):
                    if self.runtime.exists():
                        shutil.rmtree(self.runtime)
                    env = dict(self.env, NOVA_TEST_SWAP_TARGET=str(self.runtime / CSS),
                               NOVA_TEST_SOURCE=str(self.source / CSS), NOVA_TEST_LINK=link)
                    self.apply(kind, success=False, env=env)
                    self.assertTrue((self.runtime / CSS).samefile(self.source / CSS))

    def test_renderers_receive_only_runtime_root(self):
        for kind in ["curve", "hover"]:
            self.apply(kind)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        curve = next(a for a in calls if Path(a[0]).name == "curve_style.py" and a[1] == "apply")
        hover = next(a for a in calls if Path(a[0]).name == "hover_style.py")
        self.assertEqual(curve[4:], [str(self.runtime)])
        self.assertEqual(hover[4:], [str(self.runtime)])


if __name__ == "__main__":
    unittest.main()
