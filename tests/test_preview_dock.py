import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("preview_dock", REPO / "dev-tools/prepare_preview_dock.py")
dock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dock)


class PreviewDockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "metadata.json").write_text(json.dumps({"uuid": "dash-to-dock@micxgx.gmail.com", "version": 105}))
        (self.source / "dash.js").write_text(
            "    vfunc_get_preferred_height(forWidth) {\n"
            "        const [minHeight, natHeight] = super.vfunc_get_preferred_height.call(this, forWidth);\n    }\n"
            "    vfunc_get_preferred_width(forHeight) {\n"
            "        const [minWidth, natWidth] = super.vfunc_get_preferred_width.call(this, forHeight);\n    }\n")
        (self.source / "docking.js").write_text(
            "if (this.mainDock.isHorizontal && !this.settings.dockFixed)\n"
            "                    return this.mainDock.get_preferred_height(...args);")
        self.target = self.root / "preview/extension"

    def test_copy_preserves_source_and_accepts_partial_and_complete_fix(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        self.assertTrue(dock.prepare(self.source, self.target))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})
        self.assertEqual((self.target / "dash.js").read_text().count("if (!this.get_stage())"), 2)
        self.assertIn("this.mainDock.get_stage()", (self.target / "docking.js").read_text())
        dock.prepare(self.target, self.root / "already-fixed")
        (self.source / "docking.js").write_bytes((self.target / "docking.js").read_bytes())
        dock.prepare(self.source, self.root / "partially-fixed")
        for name in ("dash.js", "docking.js"):
            self.assertEqual((self.root / "already-fixed" / name).read_bytes(), (self.target / name).read_bytes())
            self.assertEqual((self.root / "partially-fixed" / name).read_bytes(), (self.target / name).read_bytes())

    def test_unexpected_source_does_not_publish_partial_copy(self):
        (self.source / "docking.js").write_text("changed upstream")
        with self.assertRaises(ValueError):
            dock.prepare(self.source, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_other_version_uses_system_extension(self):
        p = self.source / "metadata.json"
        data = json.loads(p.read_text()); data["version"] = 106
        p.write_text(json.dumps(data))
        self.assertFalse(dock.prepare(self.source, self.target))
        self.assertFalse(self.target.exists())

    def test_existing_destination_is_preserved(self):
        self.target.mkdir(parents=True)
        sentinel = self.target / "keep"
        sentinel.write_text("user data")
        with self.assertRaises(ValueError):
            dock.prepare(self.source, self.target)
        self.assertEqual(sentinel.read_text(), "user data")


class PreviewDockWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (REPO / "dev-shell-preview.sh").read_text(encoding="utf-8")

    def test_dock_is_staged_as_preview_system_extension(self):
        self.assertIn('PREVIEW_SYSTEM_DATA="$PREVIEW_ROOT/system-data"', self.script)
        self.assertIn(
            '"$PREVIEW_SYSTEM_DATA/gnome-shell/extensions/$DOCK_UUID"',
            self.script,
        )
        self.assertNotIn(
            '"$PREVIEW_DATA/gnome-shell/extensions/$DOCK_UUID"',
            self.script,
        )

    def test_preview_system_data_precedes_host_data_dirs(self):
        start = self.script.index("build_preview_data_dirs() {")
        end = self.script.index("\n}\n\nprepare_export_view()", start)
        function = self.script[start:end]
        system = 'append_preview_data_dir "$PREVIEW_SYSTEM_DATA"'
        host = 'append_preview_data_dir "$PREVIEW_HOST_EXPORT"'
        self.assertIn(system, function)
        self.assertLess(function.index(system), function.index(host))

    def test_system_extension_root_is_rebuilt_with_transient_preview_data(self):
        start = self.script.index("prepare_preview_root() {")
        end = self.script.index("\n}\n\nexport_preview_env()", start)
        function = self.script[start:end]
        self.assertIn(
            'preview_remove "$PREVIEW_CONFIG" "$PREVIEW_DATA" '
            '"$PREVIEW_SYSTEM_DATA"',
            function,
        )
        self.assertIn(
            '"$PREVIEW_SYSTEM_DATA/gnome-shell/extensions"',
            function,
        )
