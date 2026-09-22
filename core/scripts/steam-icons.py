#!/usr/bin/env python3
from __future__ import annotations
import argparse, configparser, hashlib, json, os, re, shutil, stat, subprocess, sys, tempfile
from pathlib import Path
try:
    from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageOps
except ImportError as exc:
    print('ERROR: Chybí python3-pillow.', file=sys.stderr); raise SystemExit(3) from exc
SIZES=(64,128,256,512)
STEAM_EXEC_RE=re.compile(r'(steam://(?:run|rungameid)/|\bsteam\b.*(?:-applaunch|rungameid))',re.I)
SAFE_NAME_RE=re.compile(r'^[A-Za-z0-9_.+-]+$')
BACKUP_NAME_RE=re.compile(r'^[0-9a-f]{64}\.desktop$')
def data_home(): return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
def state_home(): return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))
def parse_desktop(path):
    cp=configparser.ConfigParser(interpolation=None,strict=False); cp.optionxform=str
    try: cp.read(path,encoding='utf-8')
    except (OSError,configparser.Error): return None
    if 'Desktop Entry' not in cp: return None
    s=cp['Desktop Entry']; icon=s.get('Icon','').strip(); name=s.get('Name',path.stem); exe=s.get('Exec','')
    cats={x for x in s.get('Categories','').split(';') if x}; steam_keys=any(k.lower().startswith('x-steam') for k in s)
    candidate=icon and (STEAM_EXEC_RE.search(exe) or 'Game' in cats or path.stem.startswith('steam_app_') or steam_keys or 'seamless coop' in name.lower())
    return (cp,name,icon) if candidate else None
def score(path):
    out=0
    for x in path.parts:
        m=re.fullmatch(r'(\d+)x(\d+)',x)
        if m: out=max(out,int(m.group(1))*int(m.group(2)))
        elif x=='scalable': out=max(out,10_000_000)
    return out
def resolve(icon):
    q=Path(os.path.expandvars(os.path.expanduser(icon)))
    if q.is_absolute() and q.is_file(): return q
    names=[icon,Path(icon).stem] if Path(icon).suffix else [icon]
    roots=[data_home()/'icons/hicolor',Path.home()/'.icons/hicolor',Path('/usr/share/icons/hicolor'),data_home()/'icons',Path('/usr/share/pixmaps')]
    exts=('.png','.jpg','.jpeg','.webp','.ico'); found=[]
    for root in roots:
        if not root.is_dir(): continue
        if root.name=='pixmaps':
            for name in names:
                for ext in ('',*exts):
                    q=root/f'{name}{ext}'
                    if q.is_file(): found.append(q)
        else:
            for name in names:
                for ext in exts:
                    found.extend(root.glob(f'**/apps/{name}{ext}')); found.extend(root.glob(f'**/{name}{ext}'))
    return max(set(found),key=lambda x:(score(x),x.stat().st_size)) if found else None
def generated_name(desktop):
    slug=re.sub(r'[^A-Za-z0-9_.+-]+','-',desktop.stem).strip('-') or 'game'; digest=hashlib.sha256(str(desktop).encode()).hexdigest()[:8]
    return f'fedora-nova-game-{slug[:64]}-{digest}'
def round_icon(source,dest,size,background):
    with Image.open(source) as im: image=im.convert('RGBA')
    fitted=ImageOps.fit(image,(size,size),method=Image.Resampling.LANCZOS,centering=(.5,.5))
    result=Image.new('RGBA',(size,size),ImageColor.getrgb(background)+(255,)); result.alpha_composite(fitted)
    mask=Image.new('L',(size,size),0); ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
    result.putalpha(ImageChops.multiply(result.getchannel('A'),mask)); dest.parent.mkdir(parents=True,exist_ok=True); result.save(dest,'PNG',optimize=True)
def write_index(root,base):
    dirs=','.join(f'{s}x{s}/apps' for s in SIZES); lines=['[Icon Theme]','Name=Fedora Nova Game Icons','Comment=Ringless circular game icon overlay',f'Inherits={base},hicolor',f'Directories={dirs}','']
    for s in SIZES: lines += [f'[{s}x{s}/apps]',f'Size={s}','Context=Applications','Type=Fixed','']
    (root/'index.theme').write_text('\n'.join(lines),encoding='utf-8')
def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()
def safe_regular(path,root,label):
    path=path.absolute(); root=root.absolute()
    if not root.is_absolute() or root.is_symlink(): raise ValueError(f'Unsafe {label} root: {root}')
    try: relative=path.relative_to(root)
    except ValueError as exc: raise ValueError(f'{label} escapes its root: {path}') from exc
    current=root
    for part in relative.parts[:-1]:
        current=current/part
        if current.is_symlink() or not current.is_dir(): raise ValueError(f'Unsafe {label} parent: {current}')
    if path.is_symlink() or not path.is_file(): raise ValueError(f'Unsafe {label} file: {path}')
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1:
        raise ValueError(f'Unsafe {label} ownership/type: {path}')
    return path
def atomic_copy(source,target):
    fd,name=tempfile.mkstemp(prefix=f'.{target.name}.nova-',dir=target.parent)
    os.close(fd); temporary=Path(name)
    try:
        shutil.copy2(source,temporary,follow_symlinks=False)
        os.replace(temporary,target)
    finally: temporary.unlink(missing_ok=True)
def restore(state):
    mf=state/'desktop-overrides.json'
    if not mf.exists() and not mf.is_symlink(): return 0
    if not mf.is_file() or mf.is_symlink(): raise ValueError(f'Unsafe Steam override manifest: {mf}')
    records=json.loads(mf.read_text(encoding='utf-8'))
    if not isinstance(records,list): raise ValueError('Steam override manifest must contain a list')
    apps=data_home()/'applications'; backups=state/'desktop-backups'; validated=[]
    for r in records:
        if not isinstance(r,dict) or not all(isinstance(r.get(k),str) for k in ('target','backup','patched_sha256')):
            raise ValueError('Malformed Steam override record')
        target=safe_regular(Path(r['target']),apps,'Steam desktop target')
        backup=safe_regular(Path(r['backup']),backups,'Steam desktop backup')
        if target.suffix!='.desktop' or not BACKUP_NAME_RE.fullmatch(backup.name):
            raise ValueError('Unexpected Steam override filename')
        if sha256(target)!=r['patched_sha256']:
            raise ValueError(f'Steam desktop changed since it was patched; refusing overwrite: {target}')
        validated.append((target,backup))
    for target,backup in validated: atomic_copy(backup,target)
    mf.unlink(); return len(validated)
def patch(path,cp,name,state,records):
    apps=data_home()/'applications'; path=safe_regular(path,apps,'Steam desktop target')
    bd=state/'desktop-backups'; bd.mkdir(parents=True,exist_ok=True); backup=bd/(hashlib.sha256(str(path).encode()).hexdigest()+'.desktop')
    if backup.exists() or backup.is_symlink(): safe_regular(backup,bd,'Steam desktop backup')
    else: shutil.copy2(path,backup,follow_symlinks=False)
    cp['Desktop Entry']['Icon']=name
    fd,tmp=tempfile.mkstemp(prefix=f'.{path.name}.nova-',dir=path.parent,text=True); os.close(fd); temporary=Path(tmp)
    try:
        with temporary.open('w',encoding='utf-8') as f: cp.write(f,space_around_delimiters=False)
        os.chmod(temporary,stat.S_IMODE(path.lstat().st_mode)); os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)
    records.append({'target':str(path),'backup':str(backup),'patched_sha256':sha256(path)})
def generate(base,background):
    apps=data_home()/'applications'; theme=data_home()/'icons/Fedora-Nova-Steam'; state=state_home()/'fedora-nova/steam-icons'; state.mkdir(parents=True,exist_ok=True)
    restore(state); shutil.rmtree(theme,ignore_errors=True); theme.mkdir(parents=True); write_index(theme,base)
    generated=skipped=0; messages=[]; records=[]
    for desktop in sorted(apps.rglob('*.desktop')) if apps.is_dir() else []:
        parsed=parse_desktop(desktop)
        if not parsed: continue
        cp,name,icon=parsed; source=resolve(icon)
        if not source: skipped+=1; messages.append(f'SKIP {name}: zdroj ikony {icon} nenalezen'); continue
        icon_name=icon if SAFE_NAME_RE.fullmatch(icon) else generated_name(desktop)
        try:
            for s in SIZES: round_icon(source,theme/f'{s}x{s}/apps/{icon_name}.png',s,background)
            if icon_name!=icon: patch(desktop,cp,icon_name,state,records); messages.append(f'OK   {name}: vlastní Icon= zaoblen a launcher přesměrován')
            else: messages.append(f'OK   {name}: {icon}')
            generated+=1
        except Exception as exc: skipped+=1; messages.append(f'SKIP {name}: {exc}')
    (state/'desktop-overrides.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); (state/'base-theme').write_text(base+'\n',encoding='utf-8')
    cache=shutil.which('gtk-update-icon-cache')
    if cache: subprocess.run([cache,'-f','-t',str(theme)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return generated,skipped,messages
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('accent'); ap.add_argument('background'); ap.add_argument('--restore-desktops',action='store_true'); a=ap.parse_args(); state=state_home()/'fedora-nova/steam-icons'
    try:
        if a.restore_desktops: print(f'RESTORED desktops={restore(state)}'); return 0
        g,s,m=generate(a.base,a.background); [print(x) for x in m]; print(f'RESULT generated={g} skipped={s}'); return 0 if g else 4
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
