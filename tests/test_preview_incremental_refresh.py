import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'core/scripts'))
import preview_reload as watch
import theme_hot_reload as hot

TOKEN = 'ab' * 16


class IncrementalGtkRefresh(unittest.TestCase):
    def test_classifier_treats_gtk_theme_as_incremental(self):
        self.assertEqual(watch.classify_path('core/scripts/gtk-theme.sh'), watch.GTK_REFRESH)
        self.assertEqual(
            watch._incremental_actions([
                {'path': 'core/themes/t.css', 'action': watch.THEME_RELOAD},
                {'path': 'core/scripts/gtk-theme.sh', 'action': watch.GTK_REFRESH},
            ]),
            (watch.THEME_RELOAD, watch.GTK_REFRESH),
        )
        self.assertEqual(
            watch._incremental_actions([
                {'path': 'core/scripts/gtk-theme.sh', 'action': watch.GTK_REFRESH},
                {'path': 'core/config/profiles.json', 'action': watch.CONFIG_REFRESH},
            ]),
            (),
        )

    def test_gtk_refresh_uses_isolated_preview_environment(self):
        with tempfile.TemporaryDirectory(prefix='nova-gtk-refresh-') as tmp:
            root = Path(tmp)
            script = root / 'core/scripts/gtk-theme.sh'
            script.parent.mkdir(parents=True)
            script.write_text('#!/bin/sh\n', encoding='utf-8')
            script.chmod(0o755)
            captured = {}
            def run_checked(command, **kwargs):
                captured['command'] = command
                captured['env'] = kwargs['env']
                return ''
            with patch.object(hot, 'run_checked', run_checked), patch.dict(os.environ, {
                'HOME': '/preview/home',
                'XDG_CONFIG_HOME': '/preview/config',
                'XDG_DATA_HOME': '/preview/data',
                'XDG_STATE_HOME': '/preview/state',
            }, clear=False):
                watch._run_gtk_refresh(root)
            self.assertEqual(captured['command'], [str(script), 'refresh'])
            self.assertEqual(captured['env']['FEDORA_NOVA_APP_DIR'], str(root / 'core'))
            self.assertEqual(captured['env']['XDG_CONFIG_HOME'], '/preview/config')

    def test_mixed_theme_and_gtk_batch_runs_both_without_restart(self):
        details = [
            {'path': 'core/themes/t.css', 'action': watch.THEME_RELOAD},
            {'path': 'core/scripts/gtk-theme.sh', 'action': watch.GTK_REFRESH},
        ]
        collector = MagicMock()
        collector.__enter__.return_value = collector
        collector.pending = set()
        collector.next_batch.side_effect = [
            (watch.GTK_REFRESH, details),
            watch.SupervisorGone('done'),
        ]
        collector.pump.side_effect = lambda *args, **kwargs: None
        calls = []
        with tempfile.TemporaryDirectory(prefix='nova-mixed-refresh-') as tmp:
            root = Path(tmp)
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {'NOVA_PREVIEW_TOKEN': TOKEN}), \
                 patch.object(watch, 'Collector', return_value=collector), \
                 patch.object(watch, '_ensure_supervisor'), \
                 patch.object(hot, 'enable_subreaper'), \
                 patch.object(watch, '_run_theme_hot_reload', side_effect=lambda *a, **k: calls.append('theme') or 'Fedora-Nova-Tech'), \
                 patch.object(watch, '_run_gtk_refresh', side_effect=lambda *a, **k: calls.append('gtk')), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = watch.main(['watch-once', '--repo-root', str(root), '--supervisor-pid', str(os.getpid()), '--json'])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ['theme', 'gtk'])
        self.assertIn('GTK preview layer refreshed', err.getvalue())

    def test_refresh_does_not_turn_disabled_gtk_layer_back_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            choice = root / 'fedora-nova/current-gtk'
            choice.parent.mkdir()
            choice.write_text('off\n')
            with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(root)}), \
                 patch.object(hot, 'run_checked') as run:
                watch._run_gtk_refresh(REPO)
            self.assertEqual(run.call_args.args[0][-1], 'off')


if __name__ == '__main__':
    unittest.main()
