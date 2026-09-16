import shutil
import json
import os
import tempfile
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class FolderLayout(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gjs'), 'GJS required for real St CSS parser')
    def test_generated_style_is_accepted_by_st(self):
        # Use the installed parser: a JS mock accepts leading semicolons that
        # libcroco/St silently rejects for an empty original inline style.
        libraries = Path('/usr/lib64')
        shell = libraries / 'gnome-shell'
        mutter = sorted(libraries.glob('mutter-*/Clutter-*.typelib'))
        if not list(shell.glob('St-*.typelib')) or not mutter:
            self.skipTest('GNOME Shell St/Mutter typelibs unavailable')
        paths = f'{shell}:{mutter[-1].parent}'
        env = {**os.environ, 'GSETTINGS_BACKEND': 'memory',
               'GI_TYPELIB_PATH': paths, 'LD_LIBRARY_PATH': paths}
        module = (ROOT / 'core/themes-src/js/squircle.js').as_uri()
        source = f'import {{folderBackgroundStyle}} from {json.dumps(module)};\n' + r'''
import St from 'gi://St';
const context = new St.ThemeContext();
for (const original of [null, '', '  ', 'color: red', 'color: red;']) {
    const style = folderBackgroundStyle(original, {width:700,height:500,x:12,y:24});
    if (style.trim().startsWith(';')) throw Error('Leading empty declaration');
    const node = St.ThemeNode.new(context, context.get_root_node(), null,
        St.Widget.$gtype, null, 'app-folder-dialog', null, style);
    const [found, width] = node.lookup_length('background-size', false);
    const [positionFound, x] = node.lookup_length('background-position', false);
    if (!found || width !== 700 || !positionFound || x !== 12)
        throw Error(`St rejected generated background declarations: ${style}`);
}
print('St accepted all five original-style variants');
'''
        with tempfile.TemporaryDirectory(prefix='nova-st-parser-') as directory:
            script = Path(directory) / 'test.js'
            script.write_text(source)
            result = subprocess.run(['gjs', '-m', str(script)], env=env,
                                    text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('St accepted all five', result.stdout)

    @unittest.skipUnless(shutil.which('node'), 'Node required for adapter behavior test')
    def test_background_adapter_resize_scale_and_cleanup(self):
        result = subprocess.run(['node', '--input-type=module', '-'], cwd=ROOT, input=r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const moduleSource = readFileSync('core/themes-src/js/squircle.js');
const {calculateFolderBackground, calculateDockClearance, folderBackgroundStyle} = await import(`data:text/javascript;base64,${moduleSource.toString('base64')}`);
class Signals {
    constructor() { this.signals=new Map(); this.next=0; }
    connect(name, callback) { const id=++this.next; this.signals.set(id,{name,callback}); return id; }
    disconnect(id) { assert.ok(this.signals.delete(id)); }
    emit(name) { for (const signal of [...this.signals.values()]) if (signal.name===name) signal.callback(); }
}
class Actor extends Signals {
    constructor() { super(); this.width=0; this.height=0; this.style=null; this.writes=0; }
    has_allocation() { return this.width>0 && this.height>0; }
    get_theme_node() { return {adjust_for_height: h=>h}; }
    get_style() { return this.style; }
    set_style(style) { this.style=style; this.writes++; this.emit('notify::allocation'); }
}
class AppFolderDialog extends Signals {
    constructor() { super(); this._viewBox=new Actor(); this.child=new Actor(); }
    popup() { this._isOpen=true; return 'original-popup'; }
}
const originalPopup=AppFolderDialog.prototype.popup;
class InjectionManager {
    overrideMethod(proto,name,factory) { this.restore=()=>proto[name]=originalPopup; proto[name]=factory(proto[name]); }
    clear() { this.restore(); }
}
const context=new Signals(); context.scale_factor=1;
const St={ThemeContext:{get_for_stage:()=>context}};
const timers=new Map(); let timerId=0;
const GLib={PRIORITY_DEFAULT:0,SOURCE_CONTINUE:true,SOURCE_REMOVE:false,
 timeout_add(priority,interval,fn){timers.set(++timerId,fn);return timerId;},
 source_remove(id){timers.delete(id);}};
const Main={layoutManager:new Signals(),overview:{dash:null}};
Main.layoutManager.primaryMonitor={index:0,x:0,y:0,width:1920,height:1080};
Main.layoutManager.getWorkAreaForMonitor=()=>({x:0,y:0,width:1920,height:1080});
const shellGlobal={display:new Signals(),stage:{}};
const source=readFileSync('dev-tools/folder-layout-preview/extension.js','utf8')
    .replace(/^import .*;\n/gm,'').replace('export default class','return class');
const Adapter=new Function('St','GLib','Extension','InjectionManager','AppFolderDialog','Main',
    'calculateFolderBackground','calculateDockClearance','folderBackgroundStyle','global',source)(St,GLib,class {},InjectionManager,AppFolderDialog,
    Main,calculateFolderBackground,calculateDockClearance,folderBackgroundStyle,shellGlobal);
const adapter=new Adapter(); adapter.enable();
const dialog=new AppFolderDialog();
assert.equal(dialog.popup(),'original-popup');
assert.equal(dialog._viewBox.writes,0); // no bogus zero-size first allocation
const actor=dialog._viewBox;
actor.width=700; actor.height=500; actor.emit('notify::allocation');
assert.match(actor.style,/background-size: 700px 500px !important;/);
assert.ok(actor.style.startsWith('background-size:'));
assert.equal(actor.writes,1); // repeated allocation caused by style does not loop
assert.doesNotMatch(actor.style,/(?:^|;)\s*(?:width|height|min-width|max-width|min-height|max-height|padding):/);
assert.doesNotMatch(actor.style,/background-image:/); // existing SVG URL stays in theme
actor.width=900; actor.emit('notify::allocation');
assert.match(actor.style,/background-size: 900px 500px !important;/);
context.scale_factor=2; context.emit('notify::scale-factor');
assert.match(actor.style,/background-size: 450px 250px !important;/);
dialog.popup();
assert.equal(actor.signals.size,1); // reopening doesn't duplicate handlers
const destroyed=new AppFolderDialog(); destroyed.popup(); destroyed.emit('destroy');
assert.equal(adapter._dialogs.has(destroyed),false);
// Visible bottom dock: 24 CSS px = 48 stage px at scale 2.
Main.overview.dash={_background:{get_stage:()=>true,mapped:true,has_allocation:()=>true,
 get_transformed_position:()=>[400,980],get_transformed_size:()=>[900,80]}};
const poll=[...timers.values()][0];
assert.equal(poll(),true);
assert.match(dialog.child.style,/padding-bottom: 74px !important/);
assert.match(actor.style,/max-height: 466px !important/);
assert.equal(timers.size,1);
// A hidden dock restores the normal container and removes max-height.
Main.overview.dash._background.mapped=false;
poll();
assert.equal(dialog.child.style,null);
assert.doesNotMatch(actor.style,/max-height/);
dialog._isOpen=false;
assert.equal(poll(),false);
assert.equal(adapter._dockWatchId,0);
// Model GLib removing a source whose callback returned SOURCE_REMOVE.
timers.clear();
dialog.popup();
assert.equal(timers.size,1);
adapter.disable();
assert.equal(timers.size,0);
assert.equal(dialog.child.style,null);
assert.equal(actor.style,null);
assert.equal(actor.signals.size,0);
assert.equal(dialog.signals.size,0);
assert.equal(context.signals.size,0);
assert.equal(Main.layoutManager.signals.size,0);
assert.equal(shellGlobal.display.signals.size,0);
assert.equal(AppFolderDialog.prototype.popup,originalPopup);
''', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node required for pure JS calculations')
    def test_units_limits_and_margins(self):
        result = subprocess.run(['node', '--input-type=module', '-'], cwd=ROOT, input=r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src = readFileSync('core/themes-src/js/squircle.js');
const {toPixels, calculateFolderBackground: layout, calculateDockClearance: clearance, folderBackground} = await import(`data:text/javascript;base64,${src.toString('base64')}`);
const monitor={x:0,y:0,width:1920,height:1080};
const area={x:0,y:32,width:1920,height:1048};
const dock={x:500,y:980,width:900,height:80};
assert.deepEqual(clearance(monitor,area,dock,1),{top:32,bottom:124,maxHeight:924});
// Already reserved workarea must not subtract dock height twice.
assert.deepEqual(clearance(monitor,{...area,height:948},dock,1),{top:32,bottom:124,maxHeight:924});
assert.deepEqual(clearance(monitor,area,dock,2),{top:16,bottom:74,maxHeight:450});
assert.equal(clearance(monitor,area,null,1),null);
assert.equal(clearance(monitor,area,{...dock,x:2000},1),null);
assert.equal(clearance(monitor,area,{...dock,width:70,height:600},1),null);
assert.equal(clearance(monitor,area,{...dock,y:0},1),null);
assert.equal(clearance(monitor,area,{...dock,y:1080},1),null);
const shifted={...monitor,x:-1920,y:200};
assert.deepEqual(clearance(shifted,{...area,x:-1920,y:232},
 {...dock,x:-1420,y:1180},1),{top:32,bottom:124,maxHeight:924});
const dims = {parentSize: 500, viewportWidth: 1600, viewportHeight: 900};
for (const [value, expected] of [['80%',400],['80vw',1280],['80vh',720],['24px',24],['.5px',.5]])
    assert.equal(toPixels(value, dims), expected);
for (const value of ['auto', '20em', '-1px', '50', 50]) assert.throws(() => toPixels(value,dims));
assert.throws(() => toPixels('80%'));
const viewport = {width:1920,height:1080};
assert.throws(() => layout({width:0,height:500}, viewport));
assert.deepEqual(layout({width:700,height:500},viewport),{width:700,height:500,x:0,y:0});
assert.deepEqual(layout({width:1000,height:800},viewport,
    {...folderBackground,inset:'10%'}),{width:800,height:640,x:100,y:80});
assert.deepEqual(layout({width:1000,height:800},viewport,
    {width:'50vw',height:'50vh',inset:'24px'}),{width:952,height:540,x:24,y:130});
assert.deepEqual(layout({width:1000,height:800},viewport,
    {width:'80%',height:'50%',inset:'0px'}),{width:800,height:400,x:100,y:200});
assert.throws(() => layout({width:100,height:100},viewport,{...folderBackground,width:'0px'}));
for (const [width,height] of [[320,240],[800,600],[3840,2160],[1,1],[0.5,0.5]]) {
    const box=layout({width,height},viewport,{...folderBackground,inset:'5000px'});
    assert.ok(box.width>0 && box.height>0);
    assert.ok(box.width+2*box.x<=width);
    assert.ok(box.height+2*box.y<=height);
}
''', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_preview_staging_and_restart(self):
        source = (ROOT / 'dev-shell-preview.sh').read_text()
        self.assertIn('$CORE/themes-src/js/squircle.js', source)
        self.assertIn('$ROOT/dev-tools/folder-layout-preview/.', source)
        self.assertIn('folder-layout-preview@fedora-nova', source)
        import sys
        sys.path.insert(0, str(ROOT / 'core/scripts'))
        from preview_reload import classify_path, FULL_SHELL_RESTART
        self.assertEqual(classify_path('core/themes-src/js/squircle.js'), FULL_SHELL_RESTART)
