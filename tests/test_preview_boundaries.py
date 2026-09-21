"""Launcher path boundaries and real watcher regressions; no host settings."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'core/scripts'))
import preview_paths as paths
import preview_reload as watch
import theme_hot_reload as hot


class PreviewBoundaries(unittest.TestCase):
    def test_zombie_supervisor_is_already_stopped(self):
        source = (REPO / 'dev-shell-preview.sh').read_text()
        start = source.index('is_pid() {')
        functions = source[start:source.index('\nread_pid_file()', start)]
        child = subprocess.Popen(['true'])
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if Path(f'/proc/{child.pid}/stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                    break
                time.sleep(.01)
            else:
                self.fail('fixture did not become a zombie')
            result = subprocess.run(['bash', '-c', functions + f'\npid_alive {child.pid}'])
            self.assertEqual(result.returncode, 1)
            result = subprocess.run(['bash', '-c', functions + '\npid_alive $$'])
            self.assertEqual(result.returncode, 0)
        finally:
            child.wait()

    def test_waits_for_setsid_instead_of_recording_inherited_group(self):
        source = (REPO / 'dev-shell-preview.sh').read_text()
        start = source.index('wait_for_private_pgid() {')
        function = source[start:source.index('\n}', start) + 2]
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / 'counter'
            script = '''is_pid() { [[ "$1" =~ ^[0-9]+$ ]]; }
sleep() { :; }
pid_pgid() {
  if [[ -e "$COUNTER" ]]; then printf '%s\\n' "$1";
  else touch "$COUNTER"; echo 999999; fi
}
'''
            result = subprocess.run(['bash', '-c', script + function + '\nwait_for_private_pgid $$'],
                env={**os.environ, 'COUNTER': str(counter)}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(counter.exists())
            self.assertNotEqual(result.stdout.strip(), '999999')

    def test_display_argument_bound_to_session_token(self):
        token = 'ab' * 16
        argv = ['/usr/bin/gnome-shell', '--devkit', '--wayland',
                '--wayland-display=fedora-nova-preview-abababab']
        self.assertTrue(hot.preview_shell_argv(argv, token))
        for invalid in (argv[:-1], argv + ['--replace'],
                        argv[:-1] + ['--wayland-display=wayland-0'],
                        argv[:-1] + ['--wayland-display=fedora-nova-preview-cdcdcdcd'],
                        ['other-process', *argv[1:]]):
            self.assertFalse(hot.preview_shell_argv(invalid, token))

    def test_socket_length_fails_before_shell_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'fedora-nova-shell-preview'
            socket = root / ('x' * 108)
            result = subprocess.run([sys.executable, str(REPO / 'core/scripts/preview_paths.py'),
                'socket', str(root), str(socket)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('shorter XDG_CACHE_HOME', result.stderr)
            self.assertFalse(root.exists())

    def test_shell_exit_status_preserves_crashes(self):
        source = (REPO / 'dev-shell-preview.sh').read_text()
        start = source.index('shell_exit_status() {')
        function = source[start:source.index('\n}', start) + 2]
        for status, expected in ((0, 0), (130, 0), (143, 0), (1, 1), (133, 133)):
            result = subprocess.run(['bash', '-c', function + f'\nshell_exit_status {status}'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, expected)

    def test_stop_refuses_linked_root_or_ancestor_before_deleting_metadata(self):
        for ancestor in (False, True):
            with self.subTest(ancestor=ancestor), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                outside = base / 'outside'
                outside.mkdir()
                cache = base / 'cache'
                if ancestor:
                    cache.symlink_to(outside, target_is_directory=True)
                    root = outside / 'fedora-nova-shell-preview'
                else:
                    cache.mkdir()
                    (cache / 'fedora-nova-shell-preview').symlink_to(outside)
                    root = outside
                (root / 'runtime').mkdir(parents=True)
                token = root / 'runtime/preview.token'
                token.write_text('a' * 32 + '\n')
                result = subprocess.run([str(REPO / 'dev-shell-preview.sh'), '--stop'],
                    env={**os.environ, 'XDG_CACHE_HOME': str(cache)}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('symlink', result.stderr)
                self.assertTrue(token.exists())

    def test_cleanup_containment_idempotence_and_linked_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'fedora-nova-shell-preview'
            (root / 'data/themes').mkdir(parents=True)
            outside = Path(tmp) / 'outside'
            outside.mkdir()
            sentinel = outside / 'keep'; sentinel.write_text('safe')
            (root / 'data/themes/link').symlink_to(outside)
            paths.remove(root, [root / 'data'])  # rmtree unlinks descendants, never follows them
            paths.remove(root, [root / 'data'])
            self.assertEqual(sentinel.read_text(), 'safe')
            # abspath must not erase a link/.. traversal before link validation.
            with self.assertRaises(ValueError):
                paths.checked_path(root / 'runtime/../data')
            with self.assertRaises(ValueError): paths.remove(root, [outside])
            with self.assertRaises(ValueError): paths.remove(root, [root])
            (root / 'runtime').symlink_to(outside)
            with self.assertRaises(ValueError): paths.remove(root, [root / 'runtime/keep'])
            self.assertEqual(sentinel.read_text(), 'safe')

    def test_source_symlink_rejected_before_generators(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'theme'; source.mkdir()
            outside = Path(tmp) / 'css'; outside.write_text('unchanged')
            (source / 'gnome-shell.css').symlink_to(outside)
            with self.assertRaises(hot.HotReloadError): hot.validate_tree(source)
            self.assertEqual(outside.read_text(), 'unchanged')

    def test_tool_metadata_ignored_by_classification_and_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('.agents', '.codex', '.pytest_cache'):
                (root / name).mkdir(); (root / name / 'state').write_text('new')
                self.assertEqual(watch.classify_path(name), watch.IGNORE)
                self.assertEqual(watch.classify_path(name + '/state'), watch.IGNORE)
            self.assertEqual(watch._scan_repo_state(root), {})

    def test_collector_death_only_suppressed_when_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with watch.Collector(Path(tmp), .03, .03, 'poll') as collector:
                collector.supervisor_pid = os.getpid()
                with patch.object(watch, '_ensure_supervisor'), patch.object(hot, 'checkpoint', side_effect=hot.Cancelled()):
                    with self.assertRaises(hot.Cancelled): collector.collector_failed('EOF')
                with patch.object(watch, '_ensure_supervisor'), patch.object(hot, 'checkpoint'):
                    with self.assertRaisesRegex(RuntimeError, 'EOF'): collector.collector_failed('EOF')

    @unittest.skipUnless(shutil.which('inotifywait'), 'inotifywait unavailable')
    def test_atomic_save_and_directory_replacement_with_lost_watch(self):
        for kind in ('inotify', 'poll'):
            with self.subTest(collector=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); directory = root / 'core/themes'
                directory.mkdir(parents=True); css = directory / 'test.css'; css.write_text('old')
                with watch.Collector(root, .03, .04, kind) as collector:
                    while not collector.ready: collector.pump(.03)
                    temporary = directory / 'save.tmp'; temporary.write_text('atomic')
                    temporary.replace(css)
                    self.assertEqual(collector.next_batch()[0], watch.THEME_RELOAD)
                    shutil.rmtree(directory); directory.mkdir(); css.write_text('replacement')
                    collector.next_batch()
                    # Force missed kernel events: periodic reconciliation must
                    # still discover an edit in the replacement directory.
                    with patch.object(collector.selector, 'select', return_value=[]):
                        css.write_text('subsequent edit')
                        deadline = time.monotonic() + 2
                        while 'core/themes/test.css' not in collector.pending and time.monotonic() < deadline:
                            collector.pump(.03)
                        self.assertIn('core/themes/test.css', collector.pending)
