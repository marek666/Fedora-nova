import re
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[1]
THEMES = REPO / 'core/themes'
HOVER_SCSS = REPO / 'core/themes-src/scss/layers/_hover-circle.scss'
HOVER_RUNTIME = REPO / 'core/scripts/hover_style.py'

COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)
SHADOW_RE = re.compile(r'box-shadow\s*:\s*([^;]+);', re.S)

def strip_comments(text: str) -> str:
    return COMMENT_RE.sub('', text)

def has_top_level_comma(value: str) -> bool:
    depth = 0
    for char in value:
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif char == ',' and depth == 0:
            return True
    return False

class ShellThemeStCompatibility(unittest.TestCase):
    def shipped_theme_files(self):
        files = sorted(THEMES.glob('Fedora-Nova-*/gnome-shell/gnome-shell.css'))
        self.assertEqual(len(files), 5)
        return files

    def assert_single_st_shadows(self, text: str, *, source: str):
        bad = [match.group(1).strip() for match in SHADOW_RE.finditer(strip_comments(text))
               if has_top_level_comma(match.group(1))]
        self.assertEqual(bad, [], source)

    def test_stage_font_family_uses_st_compatible_tokens(self):
        expected = 'font-family: Inter, Adwaita Sans, sans-serif;'
        for path in self.shipped_theme_files():
            with self.subTest(theme=path.parts[-3]):
                text = strip_comments(path.read_text(encoding='utf-8'))
                self.assertIn(expected, text)
                self.assertNotIn('font-family: "Inter", "Adwaita Sans", sans-serif;', text)

    def test_shipped_themes_use_single_st_shadow(self):
        for path in self.shipped_theme_files():
            with self.subTest(theme=path.parts[-3]):
                self.assert_single_st_shadows(
                    path.read_text(encoding='utf-8'),
                    source=str(path),
                )

    def test_generated_hover_source_uses_single_st_shadow(self):
        self.assert_single_st_shadows(
            HOVER_SCSS.read_text(encoding='utf-8'),
            source=str(HOVER_SCSS),
        )

    def test_runtime_hover_generator_uses_single_st_shadow(self):
        self.assert_single_st_shadows(
            HOVER_RUNTIME.read_text(encoding='utf-8'),
            source=str(HOVER_RUNTIME),
        )

if __name__ == '__main__':
    unittest.main()
