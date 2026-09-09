from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "core" / "scripts" / "gtk-theme.sh"
BEGIN = "/* NOVA_GTK_START */"
END = "/* NOVA_GTK_END */"


class Gtk3CompatLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home with spaces"
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.state = self.root / "state"
        for path in (self.home, self.config, self.data, self.state):
            path.mkdir(parents=True, exist_ok=True)

        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_DATA_HOME": str(self.data),
                "XDG_STATE_HOME": str(self.state),
                "FEDORA_NOVA_APP_DIR": str(REPO / "core"),
            }
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def gtk3_file(self) -> Path:
        return self.config / "gtk-3.0" / "gtk.css"

    @property
    def gtk4_file(self) -> Path:
        return self.config / "gtk-4.0" / "gtk.css"

    def run_gtk(self, action: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), action],
            cwd=REPO,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def test_gtk3_layer_covers_classic_application_widgets(self) -> None:
        self.run_gtk("on")
        css = self.gtk3_file.read_text(encoding="utf-8")

        for selector in (
            "headerbar.titlebar",
            "menubar",
            "toolbar",
            "treeview.view",
            "treeview.view header button",
            "*:selected",
            "button",
            "entry",
            "menuitem:hover",
            "notebook > header",
            ".navigation-sidebar",
            "tooltip",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

        self.assertIn("@define-color theme_selected_bg_color", css)
        self.assertIn("@define-color theme_unfocused_selected_bg_color", css)
        self.assertNotIn("\n.titlebar {", css)

    def test_refresh_is_idempotent_and_preserves_user_css(self) -> None:
        self.gtk3_file.parent.mkdir(parents=True, exist_ok=True)
        self.gtk3_file.write_text("/* USER_SENTINEL */\n", encoding="utf-8")

        self.run_gtk("on")
        self.run_gtk("refresh")
        css = self.gtk3_file.read_text(encoding="utf-8")

        self.assertIn("/* USER_SENTINEL */", css)
        self.assertEqual(css.count(BEGIN), 1)
        self.assertEqual(css.count(END), 1)

    def test_off_removes_only_nova_layer(self) -> None:
        self.gtk3_file.parent.mkdir(parents=True, exist_ok=True)
        self.gtk3_file.write_text("/* USER_SENTINEL */\n", encoding="utf-8")
        self.run_gtk("on")
        self.run_gtk("off")

        css = self.gtk3_file.read_text(encoding="utf-8")
        self.assertIn("/* USER_SENTINEL */", css)
        self.assertNotIn(BEGIN, css)
        self.assertNotIn(END, css)
        self.assertEqual(
            (self.config / "fedora-nova" / "current-gtk").read_text(
                encoding="utf-8"
            ),
            "off\n",
        )

    def test_gtk4_layer_stays_separate(self) -> None:
        self.run_gtk("on")
        gtk4 = self.gtk4_file.read_text(encoding="utf-8")
        gtk3 = self.gtk3_file.read_text(encoding="utf-8")

        self.assertIn(":root {", gtk4)
        self.assertNotIn("treeview.view", gtk4)
        self.assertIn("treeview.view", gtk3)

    def test_status_reports_both_layers(self) -> None:
        self.run_gtk("on")
        status = self.run_gtk("status").stdout
        self.assertIn("GTK4 layer: yes", status)
        self.assertIn("GTK3 layer: yes", status)


if __name__ == "__main__":
    unittest.main()
