import re
from pathlib import Path
import unittest
import json
import shutil
import subprocess
import sys

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

    @unittest.skipUnless(shutil.which('sassc'), 'sassc required for rendered hover comparison')
    def test_default_hover_appearance_matches_startup_and_sass_reload(self):
        sys.path.insert(0, str(REPO / 'core/scripts'))
        import hover_style
        palette = json.loads((REPO / 'core/config/profiles.json').read_text())['profiles']['tech']
        runtime = hover_style.render('circle', palette['accent'], palette['secondary'],
                                     palette['dock_color'], palette['border'])
        compiled = subprocess.check_output(['sassc', '-t', 'expanded',
            str(REPO / 'core/themes-src/scss/profiles/tech.scss')], text=True)
        def rules(css):
            result = {}
            for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', strip_comments(css)):
                props = dict((k.strip(), re.sub(r'\s+', '', v))
                             for k, v in (part.split(':', 1) for part in body.split(';') if ':' in part))
                for selector in selectors.split(','):
                    result.setdefault(selector.strip(), {}).update(props)
            return result
        initial, refreshed = rules(runtime), rules(compiled)
        for selector, properties in [
            ('.overview-tile:hover .overview-icon > StBoxLayout > StBin', ['box-shadow', 'background-color']),
            ('#dashtodockContainer #dash .dash-item-container .app-well-app.running .overview-icon > StBoxLayout > StBin', ['box-shadow']),
            ('.app-folder .overview-icon', ['padding', 'border-radius']),
        ]:
            for prop in properties:
                with self.subTest(selector=selector, property=prop):
                    self.assertEqual(initial[selector][prop], refreshed[selector][prop])

if __name__ == '__main__':
    unittest.main()
