#!/usr/bin/env python3
from pathlib import Path
import hashlib, os, re, shutil, signal, subprocess, sys, time, urllib.request

HOME=Path.home()
DATA=HOME/'Library'/'Application Support'/'YMS Prospect Finder V3'
SRC=HOME/'Downloads'/'YMS_Prospect_Finder_V4_1_0_OTA_UPDATER_MAC'
DEST=HOME/'Applications'/'YMS Prospect Finder Runtime'
PTR=DATA/'runtime_path.txt'
PYPTR=DATA/'runtime_python.txt'
HELPER=DATA/'launcher_refresh.py'
PORT=8765
EFF_COMMIT='4b9b93fad16f30e1a9decb418aa988daabf8b8a6'
EFF_URL=f'https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/{EFF_COMMIT}/releases/5.1.1/YMS_EFFICIENCY_OS_5_1_1_FIX.py'


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def listener_pid():
    try:
        out=subprocess.check_output(['lsof','-nP','-iTCP:'+str(PORT),'-sTCP:LISTEN','-t'],text=True,stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if line.strip().isdigit(): return int(line.strip())
    except Exception: pass
    return None


def pid_command(pid):
    try:return subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:return ''


def stop_yms_listener():
    pid=listener_pid()
    if not pid:return
    cmd=pid_command(pid)
    if 'server.py' not in cmd and 'YMS' not in cmd:
        raise RuntimeError(f'Port {PORT} is occupied by a non-YMS process: {cmd}')
    print('Stopping existing YMS listener:',pid)
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:return
    end=time.time()+5
    while time.time()<end:
        if listener_pid()!=pid:return
        time.sleep(.15)
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
    time.sleep(.35)


def choose_python():
    if PYPTR.exists():
        try:
            p=Path(PYPTR.read_text('utf-8',errors='ignore').strip()).expanduser()
            if p.exists() and os.access(p,os.X_OK):return str(p)
        except Exception:pass
    for p in [sys.executable,'/opt/homebrew/bin/python3','/usr/local/bin/python3','/usr/bin/python3']:
        if p and Path(p).exists() and os.access(p,os.X_OK):return p
    raise RuntimeError('No usable Python interpreter found.')


def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={'User-Agent':'YMS-Efficiency-Runtime-Migration/5.1.2','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8')


print('\nYMS EFFICIENCY RUNTIME MIGRATION 5.1.2')
print('======================================\n')

server=SRC/'server.py';index=SRC/'index.html'
if not server.exists() or not index.exists():
    raise SystemExit('The proven Downloads runtime is missing. Nothing was changed.')
text=server.read_text('utf-8',errors='ignore')
vm=re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)',text)
version=vm.group(1) if vm else 'unknown'
print('Source runtime:',SRC)
print('Backend:',version,'·',server.stat().st_size,'bytes')
if version!='5.0.6' or server.stat().st_size<300000 or 'V5_PRODUCT_CATALOG' not in text:
    raise SystemExit('The Downloads copy is not the proven full 5.0.6 runtime. Nothing was changed.')
if 'id="outreach"' not in index.read_text('utf-8',errors='ignore'):
    raise SystemExit('The Downloads UI baseline is not recognised. Nothing was changed.')

print('\n1/5 Stopping the current YMS server...')
try:stop_yms_listener()
except Exception as ex:raise SystemExit(str(ex))

print('2/5 Moving the runtime out of macOS-protected Downloads...')
DEST.parent.mkdir(parents=True,exist_ok=True)
if DEST.exists():
    previous=DEST.with_name('YMS Prospect Finder Runtime previous '+time.strftime('%Y%m%d-%H%M%S'))
    DEST.rename(previous)
    print('Previous Applications runtime kept at:',previous)
shutil.copytree(SRC,DEST)

src_hash=sha256(SRC/'server.py');dst_hash=sha256(DEST/'server.py')
if src_hash!=dst_hash or (DEST/'server.py').stat().st_size!=(SRC/'server.py').stat().st_size:
    raise SystemExit('Runtime copy verification failed. The original Downloads copy is untouched.')
print('Verified backend copy:',dst_hash[:16]+'…')

print('3/5 Pointing YMS permanently at ~/Applications...')
DATA.mkdir(parents=True,exist_ok=True)
py=choose_python()
PTR.write_text(str(DEST),encoding='utf-8')
PYPTR.write_text(py,encoding='utf-8')
print('runtime_path.txt ->',DEST)
print('runtime_python.txt ->',py)

if HELPER.exists():
    r=subprocess.run([py,str(HELPER),str(DEST),str(DATA),py],capture_output=True,text=True,timeout=30)
    if r.returncode!=0:
        print('Launcher refresh warning:',(r.stderr or r.stdout).strip())

print('4/5 Confirming the migrated backend can start outside Downloads...')
log=HOME/'Library'/'Logs'/'YMS Prospect Finder.log';log.parent.mkdir(parents=True,exist_ok=True)
lf=open(log,'a',encoding='utf-8')
lf.write('\n--- 5.1.2 Applications runtime smoke test '+time.strftime('%Y-%m-%d %H:%M:%S')+' ---\n');lf.flush()
proc=subprocess.Popen([py,str(DEST/'server.py')],cwd=str(DEST),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
started=False
for _ in range(50):
    time.sleep(.2)
    if proc.poll() is not None:break
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/',timeout=1) as r:
            if getattr(r,'status',200)<500:
                started=True;break
    except Exception:pass
if not started:
    try:lf.flush();tail=log.read_text('utf-8',errors='ignore')[-5000:]
    except Exception:tail='[log unavailable]'
    raise SystemExit('The migrated runtime still did not start. Downloads copy remains untouched.\n\nStartup log:\n'+tail)
print('Verified: YMS starts normally from ~/Applications.')

print('5/5 Installing Efficiency OS on the migrated runtime...')
# The 5.1.1 installer will stop this smoke-test listener itself, patch the migrated
# runtime selected by runtime_path.txt, restart it, verify the served page, and open Safari.
source=fetch(EFF_URL)
if 'YMS EFFICIENCY OS 5.1.1' not in source or 'Restarting the exact YMS runtime' not in source:
    raise SystemExit('Could not verify the pinned Efficiency OS installer. Runtime migration itself is complete.')
ns={'__name__':'__main__','__file__':'/tmp/YMS_EFFICIENCY_OS_5_1_1_FROM_MIGRATION.py'}
exec(compile(source,ns['__file__'],'exec'),ns,ns)
