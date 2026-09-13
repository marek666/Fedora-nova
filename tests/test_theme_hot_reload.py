"""Isolated hot-reload regressions. Set NOVA_LIFECYCLE_TESTS=1 for fake Shell tests."""
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'core/scripts'))
import theme_hot_reload as hot
import preview_reload as watch

THEME = 'Fedora-Nova-Tech'
TOKEN = 'ac' * 16
CSS = hot.CURVE_BEGIN + '\nx {}\n' + hot.CURVE_END + '\n' + hot.HOVER_BEGIN + '\ny {}\n' + hot.HOVER_END


def put(path, text='data'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def wait_for(fn, timeout=25):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = fn()
        if value:
            return value
        time.sleep(.03)
    raise TimeoutError(str(fn))


def members(pgid):
    result = subprocess.run(['ps', '-eo', 'pid=,pgid=,stat='], capture_output=True, text=True, check=True)
    return [int(p[0]) for line in result.stdout.splitlines() if (p := line.split())[1] == str(pgid) and not p[2].startswith('Z')]


class FakeIdentity:
    theme, pid, token, value = THEME, 123, TOKEN, THEME
    def verify(self, **kw):
        pass
    def get_theme(self, **kw):
        return self.value
    def set_theme(self, name, **kw):
        self.value = name


class Primitives(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='nova-hot-unit-')
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_markers_all_or_nothing(self):
        css = put(self.root / 'theme.css', CSS)
        malformed = [CSS + hot.CURVE_BEGIN, CSS + hot.CURVE_END, CSS.replace(hot.HOVER_BEGIN, ''),
                     CSS.replace(hot.HOVER_END, ''), hot.CURVE_END + hot.CURVE_BEGIN + hot.HOVER_BEGIN + hot.HOVER_END,
                     hot.CURVE_BEGIN + hot.HOVER_BEGIN + hot.CURVE_END + hot.HOVER_END]
        for text in malformed:
            with self.subTest(text=text):
                layers = put(self.root / 'layers.css', text)
                with self.assertRaises(hot.HotReloadError):
                    hot.apply_generated_layers(css, layers)
                self.assertEqual(css.read_text(), CSS)
    def test_symlinks_and_copy_race(self):
        outside = put(self.root / 'outside.css', CSS)
        source = self.root / 'source'
        source.mkdir()
        link = source / 'gnome-shell.css'
        for target in [str(outside), '../outside.css', 'missing']:
            link.symlink_to(target)
            with self.assertRaises((hot.HotReloadError, OSError)):
                hot.copy_tree(source, self.root / 'staged')
            link.unlink()
        put(link, CSS)
        validate = hot.validate_tree
        def swap(path):
            validate(path)
            link.unlink(); link.symlink_to(outside)
        with patch.object(hot, 'validate_tree', swap):
            with self.assertRaises((hot.HotReloadError, OSError)):
                hot.copy_tree(source, self.root / 'staged')
        self.assertEqual(outside.read_text(), CSS)
    def transaction(self, phase, sig=None, fail_rollback=False):
        root = self.root / (phase + str(sig))
        staged, live = root / 'stage' / THEME, root / 'themes' / THEME
        put(staged / 'gnome-shell/gnome-shell.css', CSS + '\n/* new */')
        put(live / 'gnome-shell/gnome-shell.css', CSS)
        recovery, identity = root / 'recovery.json', FakeIdentity()
        original_set, original_rename, original_journal = identity.set_theme, hot.os.rename, hot.write_recovery
        injected = False
        def fail():
            nonlocal injected
            if injected: return
            injected = True
            if sig: os.kill(os.getpid(), sig)
            else: raise hot.HotReloadError('injected ' + phase)
        def set_theme(name, **kwargs):
            original_set(name, **kwargs)
            if not kwargs.get('rollback') and ((phase == 'unload' and name == '') or (phase == 'restore' and name)):
                fail()
        def rename(src, dst, **kwargs):
            if fail_rollback and str(src).endswith('.hot-reload-backup'):
                raise PermissionError('injected rollback failure')
            original_rename(src, dst, **kwargs)
        def journal(path, record):
            original_journal(path, record)
            if ((phase == 'before-unload' and record['phase'] == 'prepared')
                    or (phase == 'backup' and record['phase'] == 'old-backed-up')
                    or (phase == 'install' and record['phase'] == 'new-installed')):
                fail()
        with hot.cancellation_signals(), patch.object(identity, 'set_theme', set_theme), patch.object(hot.os, 'rename', rename), patch.object(hot, 'write_recovery', journal):
            with self.assertRaises(hot.HotReloadError):
                hot.replace_live_theme(staged, live, identity=identity, recovery=recovery)
        backup = live.parent / f'.{THEME}.hot-reload-backup'
        if fail_rollback:
            self.assertEqual((backup / 'gnome-shell/gnome-shell.css').read_text(), CSS)
            self.assertEqual(json.loads(recovery.read_text())['phase'], 'recovery-required')
        else:
            self.assertEqual((live / 'gnome-shell/gnome-shell.css').read_text(), CSS)
            self.assertFalse(backup.exists()); self.assertFalse(recovery.exists())
    def test_all_transaction_phases_exception_int_term(self):
        for phase in ['before-unload', 'unload', 'backup', 'install', 'restore']:
            for sig in [None, signal.SIGINT, signal.SIGTERM]:
                with self.subTest(phase=phase, signal=sig): self.transaction(phase, sig)
    def test_failed_rollback_keeps_backup(self): self.transaction('install', fail_rollback=True)
    def test_stale_backup_and_live_symlink(self):
        live, staged = self.root / 'themes' / THEME, self.root / 'staged' / THEME
        put(live / 'gnome-shell/gnome-shell.css', CSS); put(staged / 'gnome-shell/gnome-shell.css', CSS)
        backup = live.parent / f'.{THEME}.hot-reload-backup'
        put(backup / 'saved', 'last good')
        with self.assertRaises(hot.HotReloadError):
            hot.replace_live_theme(staged, live, identity=FakeIdentity(), recovery=self.root / 'recovery.json')
        self.assertEqual((backup / 'saved').read_text(), 'last good')
        shutil.rmtree(live); live.symlink_to(staged)
        with self.assertRaises(OSError):
            hot.replace_live_theme(staged, live, identity=FakeIdentity(), recovery=self.root / 'recovery.json')
    def test_bounded_descendant_reaping(self):
        hot.enable_subreaper()
        before = hot.child_pids()
        with hot.cancellation_signals(), self.assertRaisesRegex(hot.HotReloadError, 'command timed out'):
            hot.run_checked([sys.executable, '-c', 'import subprocess,time; subprocess.Popen(["sleep","30"]); time.sleep(30)'], timeout=.15)
        self.assertEqual(hot.child_pids(), before)
    def test_collectors_keep_baseline_and_ignore_generated(self):
        for kind in ['poll', 'inotify']:
            if kind == 'inotify' and not shutil.which('inotifywait'): continue
            root = self.root / kind
            css = put(root / 'core/themes/test.css', 'old')
            config = put(root / 'core/config/profiles.json', '{}')
            with watch.Collector(root, .04, .025, kind) as collector:
                wait_for(lambda: (collector.pump(.04), collector.ready)[1])
                css.write_text('first')
                self.assertEqual(collector.next_batch()[0], watch.THEME_RELOAD)
                config.write_text('before build'); collector.reconcile()
                self.assertIn('core/config/profiles.json', collector.pending)
                self.assertEqual(collector.next_batch()[0], watch.CONFIG_REFRESH)
                collector.reconcile(); config.write_text('after reconciliation')
                self.assertEqual(collector.next_batch()[0], watch.CONFIG_REFRESH)
                put(root / 'core/__pycache__/nested/foo.pyc'); collector.reconcile()
                self.assertFalse(collector.pending)
    def test_reconciliation_errors_return_restart_json(self):
        for code in [errno.EACCES, errno.EPERM, errno.EIO]:
            collector = MagicMock()
            collector.__enter__.return_value = collector
            collector.next_batch.return_value = (watch.THEME_RELOAD, [{'path': 'core/themes/t.css', 'action': watch.THEME_RELOAD}])
            collector.reconcile.side_effect = OSError(code, 'injected scan failure')
            out = io.StringIO()
            with patch.dict(os.environ, {'NOVA_PREVIEW_TOKEN': TOKEN}), patch.object(watch, 'Collector', return_value=collector), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = watch.main(['watch-once', '--repo-root', '/tmp', '--supervisor-pid', str(os.getpid()), '--json'])
            self.assertEqual(rc, 0); self.assertEqual(json.loads(out.getvalue())['action'], watch.FULL_SHELL_RESTART)
    @unittest.skipUnless(shutil.which('sassc') or shutil.which('sass'), 'Sass unavailable')
    def test_sass_default_layers_survive_and_dynamic_modes_work(self):
        core = self.root / 'core'
        for name in ['scripts', 'themes-src', 'themes', 'config']:
            shutil.copytree(REPO / 'core' / name, core / name)
        config, state = self.root / 'config', self.root / 'state'
        config.mkdir(); state.mkdir()
        curve, hover = core / 'themes-src/scss/layers/_curve.scss', core / 'themes-src/scss/layers/_hover-circle.scss'
        curve.write_text(curve.read_text().replace('border-radius: 14px;', 'border-radius: 123px;', 1))
        hover.write_text(hover.read_text().replace('transition-duration: 100ms;', 'transition-duration: 777ms;', 1))
        for dynamic in [False, True]:
            if dynamic:
                put(config / 'fedora-nova/current-curve', 'classic'); put(config / 'fedora-nova/current-hover', 'tile')
            stage, theme = hot.build_staged_theme(self.root, core, 'tech', THEME, config, state)
            try:
                css = (theme / 'gnome-shell/gnome-shell.css').read_text()
                self.assertEqual('border-radius: 123px' in css, not dynamic)
                self.assertEqual('transition-duration: 777ms' in css, not dynamic)
            finally: shutil.rmtree(stage)


class Session:
    def __init__(self, snapshot, binary, collector='inotify', symlink=False, watch_mode=True):
        self.tmp = tempfile.TemporaryDirectory(prefix='nova-hot-session-')
        self.root = Path(self.tmp.name)
        self.preview = self.root / 'cache/fedora-nova-shell-preview'
        self.runtime = self.preview / 'runtime'
        self.script = snapshot / 'dev-shell-preview.sh'
        self.env = os.environ.copy()
        for name in ['BASH_ENV', 'ENV', 'NOVA_PREVIEW_TOKEN', 'NOVA_PREVIEW_TOKEN_BOOTSTRAP_FD', 'NOVA_PREVIEW_TOKEN_BOOTSTRAP_PID']:
            self.env.pop(name, None)
        self.env.update(HOME=str(self.root / 'home'), PATH=str(binary) + ':' + os.environ['PATH'],
                        XDG_CONFIG_HOME=str(self.root / 'config'), XDG_DATA_HOME=str(self.root / 'data'),
                        XDG_CACHE_HOME=str(self.root / 'cache'), XDG_STATE_HOME=str(self.root / 'state'),
                        XDG_RUNTIME_DIR=str(self.root / 'bus-runtime'), NOVA_TEST_DIR=str(self.root),
                        NOVA_PREVIEW_WATCH_COLLECTOR=collector, NOVA_PREVIEW_WATCH_POLL_MS='100', PYTHONDONTWRITEBYTECODE='1')
        Path(self.env['HOME']).mkdir(); Path(self.env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
        executable = self.script
        if symlink:
            executable = self.root / 'fedora-nova-shell-preview'; executable.symlink_to(self.script)
        self.log = (self.root / 'output.log').open('w+')
        self.p = subprocess.Popen([str(executable), *(['--watch'] if watch_mode else []), 'tech'], env=self.env,
                                  stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.groups = set()
        try:
            wait_for(lambda: (self.root / 'ready').exists(), 35)
            wait_for(lambda: (self.runtime / 'session.env').exists())
            self.shell = int((self.root / 'ready').read_text().split()[0])
            self.groups.add(int((self.runtime / 'session.pgid').read_text()))
            self.token = (self.runtime / 'preview.token').read_text()
            if watch_mode:
                wait_for(lambda: (self.runtime / 'watcher.pgid').exists())
                self.watcher = int((self.runtime / 'watcher.pid').read_text())
                self.groups.add(int((self.runtime / 'watcher.pgid').read_text()))
            time.sleep(.5)
        except BaseException:
            self.log.flush(); print((self.root / 'output.log').read_text()[-3000:])
            self.close(); raise
    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]
    def artifacts(self):
        return list((self.preview / 'state').glob('theme-hot-reload-*')) + list((self.preview / 'data/themes').glob('.*.hot-reload-backup'))
    def reap(self):
        # Unit tests enable subreaping in this Python process. After a killed
        # supervisor its orphaned watcher/session children are therefore ours.
        output = subprocess.check_output(['ps', '-eo', 'pid=,pgid=,stat='], text=True)
        for line in output.splitlines():
            pid, group, state = line.split()
            if int(group) in self.groups and state.startswith('Z'):
                try: os.waitpid(int(pid), os.WNOHANG)
                except ChildProcessError: pass
    def stop(self):
        self.reap()
        p = subprocess.Popen([str(self.script), '--stop'], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            wait_for(lambda: (self.p.poll(), p.poll())[1] is not None, 18)
            out, err = p.communicate(timeout=1)
            self.reap()
            return p.returncode, out, err
        finally:
            if p.poll() is None: p.kill(); p.wait()
    def close(self):
        try:
            if self.p.poll() is None:
                self.p.terminate()
                try: self.p.wait(timeout=12)
                except subprocess.TimeoutExpired: self.p.kill(); self.p.wait()
            for name in ['session.pgid', 'watcher.pgid']:
                path = self.runtime / name
                if path.exists() and path.read_text().strip().isdigit(): self.groups.add(int(path.read_text()))
            for group in self.groups:
                if members(group):
                    # These groups were created and recorded by this fixture only.
                    os.killpg(group, signal.SIGKILL)
                    wait_for(lambda: not members(group), 3)
        finally:
            self.reap()
            self.log.close()
            # In particular, release each ~45k-inode Tela extraction before the next case.
            self.tmp.cleanup()


@unittest.skipUnless(os.environ.get('NOVA_LIFECYCLE_TESTS') == '1', 'opt-in fake Shell/private D-Bus tests')
class Lifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='nova-hot-integration-')
        cls.root = Path(cls.tmp.name)
        cls.snapshot = cls.root / 'repo'; cls.snapshot.mkdir()
        archive = subprocess.Popen(['git', '-C', str(REPO), 'archive', 'HEAD'], stdout=subprocess.PIPE)
        subprocess.run(['tar', '-x', '-C', str(cls.snapshot)], stdin=archive.stdout, check=True)
        archive.stdout.close(); assert archive.wait() == 0
        for name in ['preview_reload.py', 'theme_hot_reload.py', 'theme_hot_reload_core.py', 'preview_settings.py']:
            shutil.copy2(REPO / 'core/scripts' / name, cls.snapshot / 'core/scripts' / name)
        shutil.copytree(REPO / 'core/themes-src/scss', cls.snapshot / 'core/themes-src/scss', dirs_exist_ok=True)
        shutil.copy2(REPO / 'dev-shell-preview.sh', cls.snapshot / 'dev-shell-preview.sh')
        cls.binary = cls.root / 'bin'; cls.binary.mkdir()
        flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True).split()
        subprocess.run(['cc', str(REPO / 'tests/fixtures/fake-shell.c'), '-o', str(cls.binary / 'gnome-shell'), *flags], check=True)
        shutil.copy2(REPO / 'tests/fixtures/fake-gsettings.py', cls.binary / 'gsettings')
        (cls.binary / 'gsettings').chmod(0o755)
        cls.css = cls.snapshot / 'core/themes' / THEME / 'gnome-shell/gnome-shell.css'
        cls.original = cls.css.read_bytes()
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def dirty(self):
        with self.css.open('ab') as file: file.write(b'\n/* isolated hot-reload test */\n')
    def test_10_reloads_per_collector(self):
        for kind in ['inotify', 'poll']:
            with self.subTest(collector=kind):
                s = Session(self.snapshot, self.binary, kind)
                try:
                    for count in range(10):
                        before = len(s.calls()); self.dirty()
                        def reloaded():
                            if s.p.poll() is not None:
                                raise AssertionError(f"supervisor exited {s.p.returncode}")
                            return len(s.calls()) >= before + 2
                        try:
                            wait_for(reloaded)
                        except BaseException:
                            print(f"FAILED {kind} iteration {count}: " + (s.root / 'output.log').read_text()[-5000:], flush=True)
                            print(f"calls={s.calls()} artifacts={s.artifacts()}", flush=True)
                            raise
                        wait_for(lambda: not s.artifacts())
                        time.sleep(.2)
                        self.assertEqual(int((s.runtime / 'shell.pid').read_text()), s.shell)
                        self.assertEqual(int((s.runtime / 'watcher.pid').read_text()), s.watcher)
                        self.assertIsNone(s.p.poll())
                    self.assertEqual(s.stop()[0], 0)
                    s.p.wait(timeout=10)
                    self.assertFalse(any(members(g) for g in s.groups))
                    print(f'{kind}: 10 successful reloads, stable Shell/watcher PID, no artifacts/processes', flush=True)
                finally: s.close(); self.css.write_bytes(self.original)
    def test_interruptions_and_supervisor_death(self):
        for kind in ['term', 'int', 'close', 'stop', 'kill']:
            with self.subTest(action=kind):
                s = Session(self.snapshot, self.binary)
                try:
                    phase = 'unloaded' if kind == 'kill' else 'restored'
                    (s.root / phase).unlink(missing_ok=True)
                    (s.root / ('pause-' + phase)).touch()
                    self.dirty(); wait_for(lambda: (s.root / phase).exists())
                    if kind == 'close': (s.root / 'close').touch()
                    elif kind == 'stop': self.assertEqual(s.stop()[0], 0)
                    else: s.p.send_signal({'term': signal.SIGTERM, 'int': signal.SIGINT, 'kill': signal.SIGKILL}[kind])
                    s.p.wait(timeout=12)
                    if kind == 'kill':
                        watcher_group = next(g for g in s.groups if g != os.getpgid(s.shell))
                        wait_for(lambda: not members(watcher_group), 4)
                        self.assertEqual(s.stop()[0], 0)
                    else: self.assertEqual(s.p.returncode, {'term': 143, 'int': 130, 'close': 0, 'stop': 143}[kind])
                    self.assertFalse(any(members(g) for g in s.groups))
                    leftovers = [p for p in s.artifacts() if p.name != 'theme-hot-reload-recovery.json']
                    self.assertEqual(leftovers, [])
                    recovery = s.preview / 'state/theme-hot-reload-recovery.json'
                    if recovery.exists():
                        self.assertTrue(json.loads(recovery.read_text())['live_restored'])
                    print(f'{kind}: process cleanup complete; recovery={recovery.exists()}', flush=True)
                finally: s.close(); self.css.write_bytes(self.original)
    def test_identity_rejection_and_runtime_token_refusal(self):
        s = Session(self.snapshot, self.binary)
        env = hot.process_environ(s.shell)
        args = [sys.executable, '-B', str(self.snapshot / 'core/scripts/theme_hot_reload.py'),
                '--repo-root', str(self.snapshot), '--profile', 'tech', '--theme', THEME,
                '--preview-home', env['HOME'], '--preview-config', env['XDG_CONFIG_HOME'],
                '--preview-data', env['XDG_DATA_HOME'], '--preview-state', env['XDG_STATE_HOME']]
        fake = subprocess.Popen(['/usr/bin/sleep', '60'], env=env)
        try:
            before = len(s.calls())
            for pid in [fake.pid, s.p.pid, s.watcher, 99999999]:
                (s.runtime / 'shell.pid').write_text(str(pid))
                result = subprocess.run([*args, '--shell-pid', str(pid)], env=env, capture_output=True, text=True, timeout=8)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn('Traceback', result.stderr)
            (s.runtime / 'shell.pid').write_text(str(s.shell))
            self.assertEqual(len(s.calls()), before)
            with patch.dict(os.environ, env, clear=True):
                identity = hot.ShellIdentity(s.shell, s.token.strip(), Path(env['HOME']), Path(env['XDG_CONFIG_HOME']), Path(env['XDG_DATA_HOME']), Path(env['XDG_STATE_HOME']), 'tech', THEME)
                current = hot.process_identity
                def reused(pid):
                    stamp = current(pid)
                    return (stamp[0] + 1, *stamp[1:]) if pid == s.shell else stamp
                with patch.object(hot, 'process_identity', reused):
                    with self.assertRaises(hot.HotReloadError): identity.verify()
                with patch.object(identity, 'bus_pid', return_value=s.shell + 1):
                    with self.assertRaises(hot.HotReloadError): identity.verify()
                current_env = hot.process_environ
                def missing_bus(pid):
                    values = current_env(pid)
                    if pid == s.shell: values['DBUS_SESSION_BUS_ADDRESS'] = ''
                    return values
                with patch.object(hot, 'process_environ', missing_bus):
                    with self.assertRaises(hot.HotReloadError): identity.verify()
                daemon = identity.bus_pid('org.freedesktop.DBus')
                def wrong_daemon_roots(pid):
                    values = current_env(pid)
                    if pid == daemon: values['HOME'] = '/foreign-home'
                    return values
                with patch.object(hot, 'process_environ', wrong_daemon_roots):
                    with self.assertRaises(hot.HotReloadError): identity.verify()

            for token in ['', 'bad', '0' * 32]:
                result = subprocess.run([*args, '--shell-pid', str(s.shell)], env={**env, 'NOVA_PREVIEW_TOKEN': token}, capture_output=True, text=True, timeout=8)
                self.assertEqual(result.returncode, 2)
            for token in [None, 'wrong', '0' * 32]:
                if token is None: (s.runtime / 'preview.token').unlink()
                else: (s.runtime / 'preview.token').write_text(token)
                self.assertEqual(s.stop()[0], 2)
                self.assertIsNone(s.p.poll()); self.assertTrue((s.preview / 'live.lock').exists())
                put(s.runtime / 'preview.token', s.token).chmod(0o600)
            self.assertEqual(s.stop()[0], 0)
        finally: fake.terminate(); fake.wait(); s.close()
    def test_invalid_markers_restart_and_symlink_close(self):
        s = Session(self.snapshot, self.binary, symlink=True)
        try:
            self.css.write_text('/* missing markers */')
            wait_for(lambda: (s.runtime / 'shell.pid').exists() and (s.runtime / 'shell.pid').read_text().strip() not in ['', str(s.shell)], 35)
            wait_for(lambda: (s.runtime / 'watcher.pgid').exists())
            s.groups.add(int((s.runtime / 'session.pgid').read_text())); s.groups.add(int((s.runtime / 'watcher.pgid').read_text()))
            (s.root / 'close').touch(); s.p.wait(timeout=15)
            self.assertEqual(s.p.returncode, 0)
            self.assertFalse(any(members(g) for g in s.groups))
        finally: s.close(); self.css.write_bytes(self.original)

    def test_changes_during_sass_use_restart_fallback(self):
        compiler = shutil.which('sassc')
        if compiler is None: self.skipTest('sassc required for paused compiler fixture')
        profiles = self.snapshot / 'core/config/profiles.json'
        original_profiles = profiles.read_bytes()
        wrapper = self.binary / 'sassc'
        wrapper.write_text('#!/usr/bin/python3\nimport os,time\nfrom pathlib import Path\n'
                           'root=Path(os.environ["NOVA_TEST_DIR"])\n(root/"sass-paused").touch()\n'
                           'while (root/"pause-sass").exists(): time.sleep(.02)\n'
                           f'os.execv({compiler!r}, [{compiler!r}, *os.sys.argv[1:]])\n')
        wrapper.chmod(0o755)
        try:
            for kind in ['inotify', 'poll']:
                s = Session(self.snapshot, self.binary, kind)
                try:
                    (s.root / 'pause-sass').touch()
                    self.dirty(); wait_for(lambda: (s.root / 'sass-paused').exists())
                    profiles.write_bytes(original_profiles + b'\n')
                    ephemeral = self.snapshot / 'core/assets/wallpapers/nova-ephemeral.svg'
                    ephemeral.write_text('temporary event'); ephemeral.unlink()
                    time.sleep(.2)
                    (s.root / 'pause-sass').unlink()
                    wait_for(lambda: int((s.root / 'ready').read_text().split()[0]) != s.shell, 35)
                    wait_for(lambda: (s.runtime / 'watcher.pgid').exists())
                    s.groups.add(int((s.runtime / 'session.pgid').read_text()))
                    s.groups.add(int((s.runtime / 'watcher.pgid').read_text()))
                    output = (s.root / 'output.log').read_text()
                    self.assertIn('FULL_SHELL_RESTART', output)
                    self.assertIn('core/config/profiles.json', output)
                    if kind == 'inotify': self.assertIn('nova-ephemeral.svg', output)
                    self.assertEqual(s.stop()[0], 0)
                    self.assertFalse(any(members(g) for g in s.groups))
                finally:
                    s.close(); self.css.write_bytes(self.original); profiles.write_bytes(original_profiles)
        finally:
            wrapper.unlink()



class AdditionalCoverage(unittest.TestCase):
    def test_failed_recovery_prevents_session_start(self):
        script = (REPO / 'dev-shell-preview.sh').read_text()
        start = script.index('start_shell() {')
        end = script.index('\n}', start) + 2
        command = '\n'.join([
            'set -euo pipefail',
            'load_profile() { :; }',
            'prepare_preview_root() { return 2; }',
            'export_preview_env() { echo unsafe; exit 99; }',
            script[start:end],
            'if start_shell; then exit 0; else exit $?; fi',
        ])
        result = subprocess.run(['/usr/bin/bash', '-c', command], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_commit_cleanup_failure_keeps_complete_live_tree(self):
        with tempfile.TemporaryDirectory(prefix='nova-commit-test-') as tmp:
            root = Path(tmp)
            live, staged = root / 'themes' / THEME, root / 'stage' / THEME
            put(live / 'gnome-shell/gnome-shell.css', CSS)
            put(staged / 'gnome-shell/gnome-shell.css', CSS + '\n/* new */')
            remove = hot.shutil.rmtree
            def fail_backup(name, **kw):
                if str(name).endswith('.hot-reload-backup'):
                    raise PermissionError('injected backup deletion failure')
                return remove(name, **kw)
            recovery = root / 'recovery.json'
            with patch.object(hot.shutil, 'rmtree', fail_backup):
                with self.assertRaises(hot.HotReloadError):
                    hot.replace_live_theme(staged, live, identity=FakeIdentity(), recovery=recovery)
            self.assertIn('/* new */', (live / 'gnome-shell/gnome-shell.css').read_text())
            self.assertEqual(json.loads(recovery.read_text())['phase'], 'committed-cleanup-required')

    def test_runtime_lock_and_subprocess_startup_hooks(self):
        with tempfile.TemporaryDirectory(prefix='nova-lock-test-') as tmp:
            root = Path(tmp)
            with hot.transaction_lock(root):
                with self.assertRaises(hot.HotReloadError):
                    with hot.transaction_lock(root): pass
            evil = put(root / 'evil.sh', 'export NOVA_EVIL=1\nexport PATH=/evil\n')
            env = {**os.environ, 'BASH_ENV': str(evil), 'ENV': str(evil)}
            result = hot.run_checked(['/usr/bin/bash', '-c', 'printf "%s|%s" "${NOVA_EVIL-unset}" "$PATH"'], env=env)
            self.assertEqual(result, 'unset|' + os.environ['PATH'])

    def test_missing_compiler_and_missing_css_clean_staging(self):
        with tempfile.TemporaryDirectory(prefix='nova-missing-test-') as tmp:
            root = Path(tmp)
            config, state = root / 'config', root / 'state'
            config.mkdir(); state.mkdir()
            binary = root / 'bin'; binary.mkdir()
            for name in ['bash', 'dirname']:
                (binary / name).symlink_to(shutil.which(name))
            with patch.dict(os.environ, {'PATH': str(binary)}):
                with self.assertRaises(hot.HotReloadError):
                    hot.build_staged_theme(REPO, REPO / 'core', 'tech', THEME, config, state)
            self.assertEqual(list(state.iterdir()), [])
            core = root / 'core'
            for name in ['scripts', 'config', 'themes', 'themes-src']:
                shutil.copytree(REPO / 'core' / name, core / name)
            (core / 'themes' / THEME / 'gnome-shell/gnome-shell.css').unlink()
            with self.assertRaises(OSError):
                hot.build_staged_theme(root, core, 'tech', THEME, config, state)
            self.assertEqual(list(state.iterdir()), [])

    def test_standalone_cli_and_classifier(self):
        for ignored in ['foo.pyc', 'foo.pyo', 'foo.swp', 'foo.swo', 'foo~', 'foo.tmp', '.git', '.git/config', '.dev-build', '__pycache__', 'core/__pycache__/x.pyc']:
            self.assertEqual(watch.classify_path(ignored), watch.IGNORE)
        self.assertEqual(watch.classify_path('core/scripts/theme_hot_reload.py'), watch.FULL_SHELL_RESTART)
        self.assertEqual(watch.classify_paths(['core/themes/t.css', 'core/config/profiles.json'])[0], watch.CONFIG_REFRESH)
        for kind in ['poll', 'inotify']:
            with tempfile.TemporaryDirectory(prefix='nova-cli-watch-') as tmp:
                root = Path(tmp)
                css = put(root / 'core/themes/t.css', 'old')
                p = subprocess.Popen([sys.executable, '-B', str(REPO / 'core/scripts/preview_reload.py'), 'watch-once', '--repo-root', str(root), '--collector', kind, '--poll-ms', '50', '--debounce-ms', '80', '--json'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
                try:
                    time.sleep(.4); css.write_text('new')
                    out, err = p.communicate(timeout=5)
                    self.assertEqual(p.returncode, 0, err)
                    self.assertEqual(json.loads(out)['action'], watch.THEME_RELOAD)
                    self.assertEqual(len(out.splitlines()), 1)
                finally:
                    if p.poll() is None: os.killpg(p.pid, signal.SIGKILL); p.wait()

    def test_all_reload_boundaries_keep_stronger_changes(self):
        for kind in ['poll', 'inotify']:
            for phase in ['before-build', 'during-sass', 'during-staging', 'during-unload', 'during-swap', 'during-restore', 'after-reconciliation', 'before-wait']:
                with self.subTest(collector=kind, phase=phase), tempfile.TemporaryDirectory(prefix='nova-boundary-') as tmp:
                    root = Path(tmp)
                    css = put(root / 'core/themes/t.css', 'old')
                    config = put(root / 'core/config/profiles.json', '{}')
                    ran = False
                    injected = False
                    class BoundaryCollector(watch.Collector):
                        def __enter__(self):
                            while not self.ready: self.pump(.03)
                            css.write_text('theme edit')
                            return self
                        def next_batch(self):
                            nonlocal injected
                            if phase == 'before-wait' and ran and not injected:
                                config.write_text('changed'); injected = True
                            result = super().next_batch()
                            if phase == 'before-build' and not injected:
                                config.write_text('changed'); injected = True
                            return result
                        def reconcile(self):
                            nonlocal injected
                            super().reconcile()
                            if phase == 'after-reconciliation' and ran and not injected:
                                config.write_text('changed'); injected = True
                    def helper(*args, **kwargs):
                        nonlocal ran
                        ran = True
                        if phase.startswith('during-'): config.write_text('changed')
                        return THEME
                    out = io.StringIO()
                    with patch.dict(os.environ, {'NOVA_PREVIEW_TOKEN': TOKEN}), patch.object(watch, '_ensure_supervisor'), patch.object(watch, 'Collector', BoundaryCollector), patch.object(watch, '_run_theme_hot_reload', helper), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                        rc = watch.main(['watch-once', '--repo-root', str(root), '--collector', kind, '--poll-ms', '25', '--debounce-ms', '40', '--supervisor-pid', str(os.getpid()), '--json'])
                    self.assertEqual(rc, 0)
                    result = json.loads(out.getvalue())
                    self.assertIn(result['action'], [watch.CONFIG_REFRESH, watch.FULL_SHELL_RESTART])
                    self.assertIn('core/config/profiles.json', [change['path'] for change in result['changes']])

    def test_restart_preserves_backup_and_recovery(self):
        for recorded in [True, False]:
            with tempfile.TemporaryDirectory(prefix='nova-archive-test-') as tmp:
                root = Path(tmp)
                data, state, runtime = root / 'data', root / 'state', root / 'runtime'
                state.mkdir(); runtime.mkdir(mode=0o700)
                live, backup = data / 'themes' / THEME, data / 'themes' / f'.{THEME}.hot-reload-backup'
                put(live / 'content', 'new'); put(backup / 'content', 'last good')
                if recorded:
                    hot.write_recovery(state / 'theme-hot-reload-recovery.json', {'phase': 'recovery-required'})
                archive = hot.archive_recovery(data, state, runtime)
                shutil.rmtree(data); shutil.rmtree(state)
                self.assertEqual((archive / 'themes' / backup.name / 'content').read_text(), 'last good')
                self.assertEqual((archive / 'themes' / THEME / 'content').read_text(), 'new')
                self.assertTrue((archive / 'recovery.json').is_file())



if __name__ == '__main__': unittest.main()
