"""Exercise the bundled extension's actual monitor reconciliation methods."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node required for lifecycle model')
class MonitorPanelLifecycle(unittest.TestCase):
    def test_reuse_hotplug_primary_change_and_disable(self):
        result = subprocess.run(['node', '--input-type=module', '-'], cwd=ROOT,
                                text=True, capture_output=True, timeout=15, input=r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync('core/third-party/topbar-all-monitors/topbar-all-monitors@fa8i.github.io/extension.js', 'utf8');
const body = source.slice(source.indexOf('export default class')).replace('export default ', '');
let created = 0, destroyed = 0, connected = false;
class Box {
    constructor(index, monitor) { this.monitorIndex = index; created++; this.update(monitor); }
    update(monitor) { assert.ok(!this.dead); this.geometry = {...monitor}; }
    destroy() { assert.ok(!this.dead); this.dead = true; destroyed++; }
}
const layout = {
    monitors: [], primaryIndex: -1,
    connectObject(_signal, callback) { connected = true; this.changed = callback; },
    disconnectObject() { connected = false; },
};
const Component = new Function('Extension', 'Main', 'SecondaryPanelBox',
    `return (${body});`)(class {}, {layoutManager: layout}, Box);
const extension = new Component();
const monitor = (x, width = 1920) => ({x, y: 0, width, height: 1080});
const change = (monitors, primaryIndex) => {
    layout.monitors = monitors; layout.primaryIndex = primaryIndex; layout.changed();
    assert.equal(extension._panels.length, Math.max(0, monitors.length - 1));
    assert.equal(new Set(extension._panels.map(p => p.monitorIndex)).size, extension._panels.length);
    for (const panel of extension._panels) {
        assert.notEqual(panel.monitorIndex, primaryIndex);
        assert.deepEqual(panel.geometry, monitors[panel.monitorIndex]);
    }
};
extension.enable();
change([monitor(0)], 0);
assert.equal(created, 0);
change([monitor(0), monitor(1920)], 0);
const first = extension._panels[0];
for (let i = 0; i < 40; i++)
    change([monitor(0), monitor(1920, 1920 + i)], 0);
assert.equal(extension._panels[0], first);
assert.equal(created, 1); assert.equal(destroyed, 0);
change([monitor(0), monitor(1920), monitor(3840)], 0);
const third = extension._panels.find(p => p.monitorIndex === 2);
change([monitor(0), monitor(1920), monitor(3840)], 1);
assert.ok(first.dead);
assert.equal(extension._panels.find(p => p.monitorIndex === 2), third);
change([monitor(0)], 0);
change([], -1);
change([monitor(0), monitor(-1920)], 0);
extension.disable();
assert.equal(connected, false); assert.equal(created, destroyed);
extension.enable();
extension.disable();
assert.equal(created, destroyed);
console.log('PASS: geometry reuse, hotplug, primary change, zero monitors, disable/re-enable');
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
