"""NORTHBROWN 1.5.0 transition installer.

This tiny bootstrap is used only for the 1.5.0 OTA transition. The normal OTA
updater has already backed up the installed app before replacing app.py with this
file. We rebuild the 1.5.0 code from that known-good 1.4.x backup, then relaunch.
"""
from pathlib import Path
import base64, gzip, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parent
UPDATES = ROOT / 'data' / 'updates'
MARKER = UPDATES / 'northbrown-1.5.0-transition.done'


def find_legacy_root():
    candidates=[]
    for p in (UPDATES / 'backups').glob('*'):
        app=p/'app.py'
        if not app.is_file():
            continue
        try:
            text=app.read_text(encoding='utf-8', errors='ignore')
            # The full 1.4 app is large. Exclude the tiny 1.4.3 bridge itself.
            if app.stat().st_size > 50000 and "APP_VERSION = '1.4.0'" in text:
                candidates.append(p)
        except Exception:
            pass
    if not candidates:
        raise RuntimeError('Could not find the preserved NORTHBROWN 1.4 application backup. No files were changed.')
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def main():
    if MARKER.exists():
        # This should only happen if a launcher re-runs the transition file before
        # the final app.py was swapped in. Fail safely instead of looping.
        raise RuntimeError('NORTHBROWN 1.5 transition has already run. Restart NORTHBROWN.')
    legacy=find_legacy_root()
    work=Path(tempfile.mkdtemp(prefix='northbrown-150-', dir=str(UPDATES)))
    try:
        for rel in ('app.py','feature_routes.py','requirements.txt','templates/index.html','static/app.js','static/app.css'):
            src=legacy/rel
            if not src.exists():
                raise RuntimeError(f'Missing preserved file: {rel}')
            dst=work/rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src,dst)
        parts=sorted(ROOT.glob('patch150.part*'))
        if not parts:
            raise RuntimeError('NORTHBROWN 1.5 patch data is missing.')
        encoded=''.join(p.read_text(encoding='ascii').strip() for p in parts)
        diff=gzip.decompress(base64.b64decode(encoded))
        patchfile=work/'upgrade.diff'; patchfile.write_bytes(diff)
        proc=subprocess.run(['/usr/bin/patch','-p1','--batch','--forward','-i',str(patchfile)],cwd=str(work),capture_output=True,text=True)
        if proc.returncode != 0:
            raise RuntimeError('Could not apply NORTHBROWN 1.5 safely: '+(proc.stderr or proc.stdout)[-500:])
        # Compile the Python files before touching the live code.
        subprocess.run([sys.executable,'-m','py_compile',str(work/'app.py'),str(work/'feature_routes.py')],check=True,capture_output=True)
        for rel in ('app.py','feature_routes.py','requirements.txt','templates/index.html','static/app.js','static/app.css'):
            src=work/rel; dst=ROOT/rel; dst.parent.mkdir(parents=True,exist_ok=True)
            tmp=dst.with_suffix(dst.suffix+'.new'); shutil.copy2(src,tmp); os.replace(tmp,dst)
        (ROOT/'VERSION.txt').write_text('1.5.0\n',encoding='utf-8')
        MARKER.write_text(json.dumps({'installed':'1.5.0','source_backup':str(legacy)}),encoding='utf-8')
    finally:
        shutil.rmtree(work,ignore_errors=True)
    os.execv(sys.executable,[sys.executable,str(ROOT/'app.py')])


if __name__=='__main__':
    main()
