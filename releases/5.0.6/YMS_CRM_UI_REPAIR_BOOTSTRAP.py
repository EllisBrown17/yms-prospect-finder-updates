#!/usr/bin/env python3
from pathlib import Path
import os,re,shlex,signal,subprocess,sys,time,urllib.request,shutil

BASE='https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/main/releases/5.0.6/'
JS_URL=BASE+'v506_crm.js'
CSS_URL=BASE+'v506_crm.css'
DATA=Path.home()/'Library'/'Application Support'/'YMS Prospect Finder V3'
DEST=Path.home()/'Applications'/'YMS Prospect Finder'


def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={'User-Agent':'YMS-CRM-Canonical-Repair/2','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8')

def is_yms_server(p):
    try:
        if not p.exists() or p.name!='server.py' or p.stat().st_size<50000:return False
        t=p.read_text('utf-8',errors='ignore')
        return 'V5_PRODUCT_CATALOG' in t or 'YMS Prospect Finder' in t
    except:return False

def proc_server(cmd,pid):
    cwd=None
    try:
        out=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True,stderr=subprocess.DEVNULL)
        for x in out.splitlines():
            if x.startswith('n') and len(x)>1:cwd=Path(x[1:]);break
    except:pass
    try:parts=shlex.split(cmd)
    except:parts=cmd.split()
    for t in parts:
        if t.endswith('server.py'):
            p=Path(t).expanduser()
            if not p.is_absolute() and cwd:p=cwd/p
            if p.exists():return p.resolve()
    if cwd and (cwd/'server.py').exists():return (cwd/'server.py').resolve()

def stop_all_yms():
    try:out=subprocess.check_output(['ps','ax','-o','pid=,command='],text=True,errors='ignore')
    except:return
    victims=[]
    for line in out.splitlines():
        m=re.match(r'\s*(\d+)\s+(.*)',line)
        if not m:continue
        pid=int(m.group(1));cmd=m.group(2)
        if 'server.py' not in cmd:continue
        p=proc_server(cmd,pid)
        if p and is_yms_server(p):victims.append(pid)
    for pid in victims:
        try:os.kill(pid,signal.SIGTERM)
        except:pass
    end=time.time()+4
    while time.time()<end:
        alive=[]
        for pid in victims:
            try:os.kill(pid,0);alive.append(pid)
            except:pass
        if not alive:return
        time.sleep(.15)
    for pid in victims:
        try:os.kill(pid,signal.SIGKILL)
        except:pass

def find_base():
    c=[]
    root=DATA/'update-backups'
    for p in root.glob('before-5.0.6-recovery-*') if root.exists() else []:
        s=p/'server.py';h=p/'index.html'
        if not s.exists() or not h.exists() or s.stat().st_size<50000:continue
        try:
            st=s.read_text('utf-8',errors='ignore');ht=h.read_text('utf-8',errors='ignore')
        except:continue
        if 'V5_PRODUCT_CATALOG' not in st or 'id="prospects"' not in ht or 'id="outreach"' not in ht:continue
        c.append((p.stat().st_mtime,p))
    if not c:
        for p in root.glob('before-5.0.6-*') if root.exists() else []:
            s=p/'server.py';h=p/'index.html'
            if s.exists() and h.exists() and s.stat().st_size>=50000:
                try:
                    if 'V5_PRODUCT_CATALOG' in s.read_text('utf-8',errors='ignore') and 'id="prospects"' in h.read_text('utf-8',errors='ignore'):c.append((p.stat().st_mtime,p))
                except:pass
    return max(c,key=lambda x:x[0])[1] if c else None

def port_for_pid(pid):
    try:
        out=subprocess.check_output(['lsof','-Pan','-p',str(pid),'-iTCP','-sTCP:LISTEN'],text=True,stderr=subprocess.DEVNULL)
        m=re.search(r'(?:127\.0\.0\.1|localhost|\*):(\d+)',out)
        return int(m.group(1)) if m else None
    except:return None

def find_canonical_process():
    try:out=subprocess.check_output(['ps','ax','-o','pid=,command='],text=True,errors='ignore')
    except:return None,None
    for line in out.splitlines():
        m=re.match(r'\s*(\d+)\s+(.*)',line)
        if not m:continue
        pid=int(m.group(1));cmd=m.group(2)
        if str(DEST/'server.py') in cmd:
            p=port_for_pid(pid)
            if p:return pid,p
    return None,None

print('\nYMS 5.0.6 CLEAN CRM REPAIR')
print('==========================\n')
base=find_base()
if not base:
    raise SystemExit('Could not find the known-good V5 backup. Nothing was changed.')
print('Using safe V5 base:',base)
print('This does not modify your prospect/settings data folder.\n')

print('1/5 Stopping stray YMS servers...')
stop_all_yms()

print('2/5 Building one clean YMS application...')
if DEST.exists():
    old=DEST.with_name('YMS Prospect Finder previous '+time.strftime('%Y%m%d-%H%M%S'))
    DEST.rename(old)
    print('Previous clean app kept at:',old)
DEST.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree(base,DEST)
server=DEST/'server.py';index=DEST/'index.html'

st=server.read_text('utf-8',errors='ignore')
st,n=re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "5.0.6"',st,count=1)
if n!=1:raise SystemExit('Could not set app version safely.')
server.write_text(st,encoding='utf-8')

print('3/5 Adding the CRM tab + bulk Emailed controls...')
js=fetch(JS_URL);css=fetch(CSS_URL)
old='''  function findNavButton(label){\n    return [...document.querySelectorAll('button,a,[role="tab"]')].find(e=>(e.textContent||'').trim().replace(/\\s+\\d+$/,'').toLowerCase()===label.toLowerCase());\n  }'''
new='''  function findNavButton(label){\n    const q=String(label||'').toLowerCase();\n    const els=[...document.querySelectorAll('button,a,[role="tab"],[onclick],[data-tab],[data-view]')];\n    return els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('href'),e.getAttribute('data-tab'),e.getAttribute('data-view'),e.id].filter(Boolean).join(' ').toLowerCase();return s.includes(q)}) || els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('data-tab'),e.id].filter(Boolean).join(' ').toLowerCase();return /prospect|product|discover|dashboard|settings/.test(s)});\n  }'''
if old in js:js=js.replace(old,new,1)
html=index.read_text('utf-8',errors='ignore')
if 'v504CrmDashboard' not in html and 'V5.0.4 CRM + smart follow-up layer' not in html:
    raise SystemExit('The safe V5 base is missing the 5.0.5 CRM foundation. Clean app was not launched.')
start='<!-- YMS CRM CANONICAL 5.0.6 START -->';end='<!-- YMS CRM CANONICAL 5.0.6 END -->'
html=re.sub(re.escape(start)+r'.*?'+re.escape(end),'',html,flags=re.S)
block=start+'\n<style>\n'+css+'\n</style>\n<script>\n'+js+'\n</script>\n'+end
html=html.replace('</body>',block+'\n</body>',1) if '</body>' in html else html+'\n'+block
html=re.sub(r'<title>YMS Prospect Finder V[^<]+</title>','<title>YMS Prospect Finder V5.0.6 Mac — YMS-Tools</title>',html,count=1)
html=re.sub(r'<b id="versionLabel">[^<]*</b>','<b id="versionLabel">V5.0.6</b>',html,count=1)
if 'v506CrmNav' not in html or 'v506BulkBar' not in html:raise SystemExit('CRM injection validation failed.')
index.write_text(html,encoding='utf-8')

print('4/5 Starting only the clean YMS copy...')
log=DEST/'YMS_STARTUP.log'
lf=open(log,'w',encoding='utf-8')
proc=subprocess.Popen([sys.executable,str(server)],cwd=str(DEST),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
pid=proc.pid;port=None
for _ in range(100):
    time.sleep(.15)
    cp,pp=find_canonical_process()
    if cp and pp:pid,port=cp,pp;break
    if proc.poll() is not None:break
if not port:
    try:lf.flush()
    except:pass
    tail=''
    try:tail=log.read_text('utf-8',errors='ignore')[-6000:]
    except:pass
    raise SystemExit('\nClean YMS did not start. Exact startup log:\n'+(tail or '[log was empty]'))

print('5/5 Creating a fresh Desktop launcher...')
launcher=Path.home()/'Desktop'/'YMS Prospect Finder.command'
launcher.write_text('#!/bin/bash\ncd "$HOME/Applications/YMS Prospect Finder"\nexec "'+sys.executable+'" server.py\n',encoding='utf-8')
os.chmod(launcher,0o755)
url=f'http://127.0.0.1:{port}/?crmclean={int(time.time())}'
print('\nSUCCESS — clean YMS 5.0.6 is running.')
print('App:',DEST)
print('URL:',url)
print('Desktop launcher:',launcher)
try:subprocess.Popen(['open',url])
except:pass
print('\nYou should now have a separate CRM tab and Bulk CRM / Emailed controls in Prospects.')
