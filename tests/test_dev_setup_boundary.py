from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]
SETUP = REPO / "dev-setup-fedora.sh"
BUILDER_DOC = REPO / "docs/BUILDER.md"


class DevSetupBoundaryTests(unittest.TestCase):
    def test_dev_setup_does_not_install_global_shell_preview_helper(self) -> None:
        source = SETUP.read_text(encoding="utf-8")
        self.assertNotIn(".local/bin/fedora-nova-shell-preview", source)
        self.assertNotIn('ln -sfn "$ROOT/dev-shell-preview.sh"', source)
        self.assertIn("./dev-shell-preview.sh tech", source)

    def test_builder_docs_keep_shell_preview_checkout_local(self) -> None:
        docs = BUILDER_DOC.read_text(encoding="utf-8")
        self.assertIn("does not install a global Shell Preview helper", docs)
        self.assertIn("run `./dev-shell-preview.sh` from the checkout", docs)


if __name__ == "__main__":
    unittest.main()
