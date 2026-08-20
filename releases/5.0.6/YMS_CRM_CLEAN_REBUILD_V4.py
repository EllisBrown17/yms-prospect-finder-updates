#!/usr/bin/env python3
from pathlib import Path
import os,re,shlex,signal,subprocess,sys,time,urllib.request,shutil

# Pin the actual CRM assets to a known commit so this repair cannot pick up a stale main-branch copy.
ASSET_COMMIT='10e6f10a7ecbfe8048fc301d92527d80b7f3d1ed'
BASE=f'https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/{ASSET_COMMIT}/releases/5.0.6/'
JS_URL=BASE+'v506_crm.js'
CSS_URL=BASE+'v506_crm.css'
DATA=Path.home()/'Library'/'Application Support'/'YMS Prospect Finder V3'
DEST=Path.home()/'Applications'/'YMS Prospect Finder'


def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={
        'User-Agent':'YMS-CRM-Canonical-Repair/4',
        'Cache-Control':'no-cache','Pragma':'no-cache'
    })
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode('utf-8')


def is_yms_server(p):
    try:
        if not p.exists() or p.name!='server.py' or p.stat().st_size<50000:
            return False
        t=p.read_text('utf-8',errors='ignore')
        return 'V5_PRODUCT_CATALOG' in t or 'YMS Prospect Finder' in t
    except Exception:
        return False


def proc_server(cmd,pid):
    cwd=None
    try:
        out=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True,stderr=subprocess.DEVNULL)
        for x in out.splitlines():
            if x.startswith('n') and len(x)>1:
                cwd=Path(x[1:]);break
    except Exception:
        pass
    try:
        parts=shlex.split(cmd)
    except Exception:
        parts=cmd.split()
    for t in parts:
        if t.endswith('server.py'):
            p=Path(t).expanduser()
            if not p.is_absolute() and cwd:
                p=cwd/p
            if p.exists():
                return p.resolve()
    if cwd and (cwd/'server.py').exists():
        return (cwd/'server.py').resolve()


def stop_all_yms():
    try:
        out=subprocess.check_output(['ps','ax','-o','pid=,command='],text=True,errors='ignore')
    except Exception:
        return
    victims=[]
    for line in out.splitlines():
        m=re.match(r'\s*(\d+)\s+(.*)',line)
        if not m: continue
        pid=int(m.group(1));cmd=m.group(2)
        if 'server.py' not in cmd: continue
        p=proc_server(cmd,pid)
        if p and is_yms_server(p):
            victims.append(pid)
    for pid in victims:
        try: os.kill(pid,signal.SIGTERM)
        except Exception: pass
    end=time.time()+4
    while time.time()<end:
        alive=[]
        for pid in victims:
            try: os.kill(pid,0);alive.append(pid)
            except Exception: pass
        if not alive: return
        time.sleep(.15)
    for pid in victims:
        try: os.kill(pid,signal.SIGKILL)
        except Exception: pass


def find_base():
    root=DATA/'update-backups'
    candidates=[]
    if not root.exists():
        return None
    # Prefer backups taken immediately before any 5.0.6 attempt.
    patterns=['before-5.0.6-recovery-*','before-5.0.6-*','before-5.0.5-*','before-5.0.3-*']
    seen=set()
    for pattern in patterns:
        for p in root.glob(pattern):
            if p in seen: continue
            seen.add(p)
            s=p/'server.py';h=p/'index.html'
            if not s.exists() or not h.exists() or s.stat().st_size<50000:
                continue
            try:
                st=s.read_text('utf-8',errors='ignore')
                ht=h.read_text('utf-8',errors='ignore')
            except Exception:
                continue
            if 'V5_PRODUCT_CATALOG' not in st:
                continue
            if 'id="prospects"' not in ht or 'id="outreach"' not in ht:
                continue
            vm=re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)',st)
            ver=vm.group(1) if vm else 'unknown'
            candidates.append((p.stat().st_mtime,p,ver))
        if candidates:
            # The first pattern that yields valid V5 backups is the preferred family.
            break
    return max(candidates,key=lambda x:x[0]) if candidates else None


def port_for_pid(pid):
    try:
        out=subprocess.check_output(['lsof','-Pan','-p',str(pid),'-iTCP','-sTCP:LISTEN'],text=True,stderr=subprocess.DEVNULL)
        m=re.search(r'(?:127\.0\.0\.1|localhost|\*):(\d+)',out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def find_canonical_process():
    try:
        out=subprocess.check_output(['ps','ax','-o','pid=,command='],text=True,errors='ignore')
    except Exception:
        return None,None
    target=str(DEST/'server.py')
    for line in out.splitlines():
        m=re.match(r'\s*(\d+)\s+(.*)',line)
        if not m: continue
        pid=int(m.group(1));cmd=m.group(2)
        if target in cmd:
            p=port_for_pid(pid)
            if p: return pid,p
    return None,None


def strengthen_crm_js(js):
    # The 5.0.6 asset formats findNavButton as a one-line function. Do not depend on whitespace.
    start=js.find('function findNavButton(label)')
    end=js.find('function ensureCrmNav', start if start>=0 else 0)
    if start<0 or end<0 or end<=start:
        raise RuntimeError('Could not locate the CRM navigation helper in the verified 5.0.6 JS.')
    replacement='''function findNavButton(label){\n    const q=String(label||'').toLowerCase();\n    const els=[...document.querySelectorAll('button,a,[role="tab"],[onclick],[data-tab],[data-view]')];\n    const exact=els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('href'),e.getAttribute('data-tab'),e.getAttribute('data-view'),e.id].filter(Boolean).join(' ').toLowerCase();return s.includes(q)});\n    if(exact)return exact;\n    return els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('data-tab'),e.getAttribute('data-view'),e.id].filter(Boolean).join(' ').toLowerCase();return /outreach|prospect|product|discover|dashboard|settings/.test(s)});\n  }\n  '''
    return js[:start]+replacement+js[end:]


print('\nYMS 5.0.6 CLEAN CRM REPAIR V4')
print('==============================\n')
base_info=find_base()
if not base_info:
    raise SystemExit('Could not find a known-good full V5 backup. Nothing was changed.')
_,base,base_version=base_info
print('Using safe V5 base:',base)
print('Base version:',base_version)
print('Prospect/settings data folder is not modified.\n')

print('1/6 Stopping stray YMS servers...')
stop_all_yms()

print('2/6 Building one clean YMS application...')
if DEST.exists():
    old=DEST.with_name('YMS Prospect Finder previous '+time.strftime('%Y%m%d-%H%M%S'))
    DEST.rename(old)
    print('Previous clean app kept at:',old)
DEST.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree(base,DEST)
server=DEST/'server.py';index=DEST/'index.html'

st=server.read_text('utf-8',errors='ignore')
st,n=re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "5.0.6"',st,count=1)
if n!=1:
    raise SystemExit('Could not set the clean app version safely.')
server.write_text(st,encoding='utf-8')

print('3/6 Downloading and strengthening the verified CRM UI...')
js=fetch(JS_URL);css=fetch(CSS_URL)
if 'v506CrmNav' not in js or 'v506BulkBar' not in js:
    raise SystemExit('Verified CRM assets failed validation. Clean app was not launched.')
try:
    js=strengthen_crm_js(js)
except Exception as ex:
    raise SystemExit(str(ex)+' Clean app was not launched.')

print('4/6 Injecting CRM tab + bulk Emailed controls...')
html=index.read_text('utf-8',errors='ignore')
start='<!-- YMS CRM CANONICAL 5.0.6 V4 START -->';end='<!-- YMS CRM CANONICAL 5.0.6 V4 END -->'
# Remove any earlier canonical repair blocks from previous attempts in this copied base.
html=re.sub(r'<!-- YMS CRM CANONICAL 5\.0\.6(?: V\d+)? START -->.*?<!-- YMS CRM CANONICAL 5\.0\.6(?: V\d+)? END -->','',html,flags=re.S)
block=start+'\n<style>\n'+css+'\n</style>\n<script>\n'+js+'\n</script>\n'+end
html=html.replace('</body>',block+'\n</body>',1) if '</body>' in html else html+'\n'+block
html=re.sub(r'<title>YMS Prospect Finder V[^<]+</title>','<title>YMS Prospect Finder V5.0.6 Mac — YMS-Tools</title>',html,count=1)
html=re.sub(r'<b id="versionLabel">[^<]*</b>','<b id="versionLabel">V5.0.6</b>',html,count=1)
if 'YMS CRM CANONICAL 5.0.6 V4 START' not in html or 'v506CrmNav' not in html or 'v506BulkBar' not in html:
    raise SystemExit('CRM injection validation failed. Clean app was not launched.')
index.write_text(html,encoding='utf-8')

print('5/6 Starting only the clean YMS copy...')
log=DEST/'YMS_STARTUP.log'
lf=open(log,'w',encoding='utf-8')
proc=subprocess.Popen([sys.executable,str(server)],cwd=str(DEST),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
port=None
for _ in range(100):
    time.sleep(.15)
    cp,pp=find_canonical_process()
    if cp and pp:
        port=pp;break
    if proc.poll() is not None:
        break
if not port:
    try: lf.flush()
    except Exception: pass
    try: tail=log.read_text('utf-8',errors='ignore')[-6000:]
    except Exception: tail='[log unavailable]'
    raise SystemExit('\nClean YMS did not start. Exact startup log:\n'+tail)

# Verify what the browser will actually receive, not just the files on disk.
try:
    check_url=f'http://127.0.0.1:{port}/?verifycrm={int(time.time())}'
    req=urllib.request.Request(check_url,headers={'Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=8) as r:
        served=r.read().decode('utf-8',errors='ignore')
    if 'YMS CRM CANONICAL 5.0.6 V4 START' not in served or 'v506CrmNav' not in served or 'v506BulkBar' not in served:
        raise RuntimeError('The running server did not serve the CRM-patched page.')
    print('Verified: running page contains CRM + bulk controls.')
except Exception as ex:
    raise SystemExit('Clean YMS started, but served-page CRM verification failed: '+str(ex))

print('6/6 Creating a fresh Desktop launcher...')
launcher=Path.home()/'Desktop'/'YMS Prospect Finder.command'
launcher.write_text('#!/bin/bash\ncd "$HOME/Applications/YMS Prospect Finder"\nexec "'+sys.executable+'" server.py\n',encoding='utf-8')
os.chmod(launcher,0o755)
url=f'http://127.0.0.1:{port}/?crmclean={int(time.time())}'
print('\nSUCCESS — clean YMS 5.0.6 with CRM is running.')
print('App:',DEST)
print('URL:',url)
print('Desktop launcher:',launcher)
try: subprocess.Popen(['open',url])
except Exception: pass
print('\nExpected UI: CRM in the top navigation; Bulk CRM / Emailed controls in Prospects.')
