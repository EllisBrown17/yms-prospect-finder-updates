#!/usr/bin/env python3
from pathlib import Path
import os,re,signal,subprocess,sys,time,urllib.request

HOME=Path.home()
DATA=HOME/'Library'/'Application Support'/'YMS Prospect Finder V3'
DEST=HOME/'Applications'/'YMS Prospect Finder Runtime'
PTR=DATA/'runtime_path.txt'
PYPTR=DATA/'runtime_python.txt'
HELPER=DATA/'launcher_refresh.py'
PORT=8765
EFF_COMMIT='4b9b93fad16f30e1a9decb418aa988daabf8b8a6'
EFF_URL=f'https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/{EFF_COMMIT}/releases/5.1.1/YMS_EFFICIENCY_OS_5_1_1_FIX.py'
LOG=Path('/tmp/YMS_5_1_3_APPLICATIONS_START.log')


def listener_pids():
    try:
        out=subprocess.check_output(['lsof','-nP','-iTCP:'+str(PORT),'-sTCP:LISTEN','-t'],text=True,stderr=subprocess.DEVNULL)
        return [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
    except Exception:return []


def cmd(pid):
    try:return subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:return ''


def exact_dest_listener():
    target=str((DEST/'server.py').resolve())
    for pid in listener_pids():
        c=cmd(pid)
        if target in c:return pid
    return None


def stop_yms_listeners():
    for pid in listener_pids():
        c=cmd(pid)
        if 'server.py' not in c and 'YMS' not in c:
            raise RuntimeError(f'Port {PORT} is occupied by a non-YMS process: {c}')
        print('Stopping stale YMS listener:',pid,c)
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:continue
    deadline=time.time()+8
    while time.time()<deadline:
        if not listener_pids():return
        time.sleep(.2)
    for pid in listener_pids():
        c=cmd(pid)
        if 'server.py' in c or 'YMS' in c:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
    time.sleep(.5)


def choose_python():
    if PYPTR.exists():
        try:
            p=Path(PYPTR.read_text('utf-8',errors='ignore').strip()).expanduser()
            if p.exists() and os.access(p,os.X_OK):return str(p)
        except Exception:pass
    for p in ['/opt/homebrew/bin/python3','/usr/local/bin/python3','/usr/bin/python3',sys.executable]:
        if p and Path(p).exists() and os.access(p,os.X_OK):return p
    raise RuntimeError('No usable Python interpreter found.')


def page_ok():
    try:
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}/?runtimecheck={int(time.time())}',headers={'Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=4) as r:
            return getattr(r,'status',200)<500
    except Exception:return False


def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={'User-Agent':'YMS-Efficiency-Finalise/5.1.3','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8')

print('\nYMS EFFICIENCY RUNTIME FINALISE 5.1.3')
print('=====================================\n')
SERVER=DEST/'server.py';INDEX=DEST/'index.html'
if not SERVER.exists() or not INDEX.exists():
    raise SystemExit('The migrated Applications runtime is missing. Nothing was changed.')
text=SERVER.read_text('utf-8',errors='ignore')
vm=re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)',text)
ver=vm.group(1) if vm else 'unknown'
print('Runtime:',DEST)
print('Backend:',ver,'·',SERVER.stat().st_size,'bytes')
if ver!='5.0.6' or SERVER.stat().st_size<300000 or 'V5_PRODUCT_CATALOG' not in text:
    raise SystemExit('The Applications runtime is not the proven full 5.0.6 backend. Nothing was changed.')

py=choose_python()
print('Python:',py)

print('\n1/5 Removing copied macOS quarantine metadata...')
try:subprocess.run(['/usr/bin/xattr','-dr','com.apple.quarantine',str(DEST)],timeout=20,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
except Exception:pass
try:subprocess.run(['/bin/chmod','-R','u+rwX',str(DEST)],timeout=20,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
except Exception:pass

print('2/5 Verifying backend syntax before launch...')
r=subprocess.run([py,'-m','py_compile',str(SERVER)],cwd=str(DEST),capture_output=True,text=True,timeout=30)
if r.returncode!=0:
    raise SystemExit('Backend syntax check failed:\n'+(r.stderr or r.stdout))
print('Syntax OK.')

print('3/5 Making Applications the only YMS runtime...')
DATA.mkdir(parents=True,exist_ok=True)
PTR.write_text(str(DEST),encoding='utf-8');PYPTR.write_text(py,encoding='utf-8')
if HELPER.exists():
    rr=subprocess.run([py,str(HELPER),str(DEST),str(DATA),py],capture_output=True,text=True,timeout=30)
    if rr.returncode!=0:print('Launcher refresh warning:',(rr.stderr or rr.stdout).strip())
stop_yms_listeners()

print('4/5 Starting the Applications runtime — allowing up to 90 seconds...')
LOG.write_text('YMS 5.1.3 Applications runtime startup '+time.strftime('%Y-%m-%d %H:%M:%S')+'\n',encoding='utf-8')
lf=open(LOG,'a',encoding='utf-8')
proc=subprocess.Popen([py,'-u',str(SERVER)],cwd=str(DEST),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
verified=False
stolen=False
for i in range(360):
    time.sleep(.25)
    if proc.poll() is not None:break
    pids=listener_pids()
    if pids:
        exact=exact_dest_listener()
        if exact and page_ok():
            verified=True;break
        if not exact:
            stolen=True;break
    if i in (39,119,239):print(f'  still starting… {int((i+1)*.25)}s')

if stolen:
    bad=[(p,cmd(p)) for p in listener_pids()]
    try:proc.terminate()
    except Exception:pass
    raise SystemExit('Another YMS process stole port 8765 before the Applications runtime could start:\n'+repr(bad)+'\nNo UI changes were made.')
if not verified:
    try:lf.flush()
    except Exception:pass
    tail=''
    try:tail=LOG.read_text('utf-8',errors='ignore')[-7000:]
    except Exception:pass
    state='still running' if proc.poll() is None else f'exited with code {proc.returncode}'
    raise SystemExit(f'Applications runtime did not become ready within the startup window ({state}).\nExact NEW-process log:\n'+(tail or '[empty]'))
print('Verified listener PID:',exact_dest_listener())
print('Verified: port 8765 belongs to ~/Applications/YMS Prospect Finder Runtime.')

print('5/5 Installing Efficiency OS with the same robust startup window...')
source=fetch(EFF_URL)
if 'YMS EFFICIENCY OS 5.1.1' not in source or 'for _ in range(80):' not in source:
    raise SystemExit('Could not validate the pinned Efficiency installer. Runtime itself is now fixed and running.')
# Increase the Efficiency installer restart verification from 20s to 90s.
source=source.replace('for _ in range(80):','for _ in range(360):',1)
# Use a clean per-attempt log rather than historical noise.
source=source.replace("log=HOME/'Library'/'Logs'/'YMS Prospect Finder.log'","log=Path('/tmp/YMS_EFFICIENCY_5_1_3_RESTART.log')",1)
compile(source,'/tmp/YMS_EFFICIENCY_5_1_3_INSTALLER.py','exec')
ns={'__name__':'__main__','__file__':'/tmp/YMS_EFFICIENCY_5_1_3_INSTALLER.py'}
exec(compile(source,ns['__file__'],'exec'),ns,ns)
