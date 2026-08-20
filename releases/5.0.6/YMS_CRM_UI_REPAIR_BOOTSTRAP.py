#!/usr/bin/env python3
from pathlib import Path
import os,re,shlex,signal,subprocess,sys,time,urllib.request

BASE='https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/main/releases/5.0.6/'
JS_URL=BASE+'v506_crm.js'
CSS_URL=BASE+'v506_crm.css'

def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={'User-Agent':'YMS-CRM-Repair','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8')

def cwd(pid):
    try:
        out=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True,stderr=subprocess.DEVNULL)
        for x in out.splitlines():
            if x.startswith('n'):return Path(x[1:])
    except:pass

def port(pid):
    try:
        out=subprocess.check_output(['lsof','-Pan','-p',str(pid),'-iTCP','-sTCP:LISTEN'],text=True,stderr=subprocess.DEVNULL)
        m=re.search(r'(?:127\.0\.0\.1|\*):(\d+)',out)
        return int(m.group(1)) if m else None
    except:return None

def server_from(cmd,pid):
    c=cwd(pid)
    try:parts=shlex.split(cmd)
    except:parts=cmd.split()
    for t in parts:
        if t.endswith('server.py'):
            p=Path(t).expanduser()
            if not p.is_absolute() and c:p=c/p
            if p.exists():return p.resolve()
    if c and (c/'server.py').exists():return (c/'server.py').resolve()

def find_running():
    out=subprocess.check_output(['ps','ax','-o','pid=,command='],text=True,errors='ignore')
    rows=[]
    for line in out.splitlines():
        m=re.match(r'\s*(\d+)\s+(.*)',line)
        if not m:continue
        pid=int(m.group(1));cmd=m.group(2)
        if 'server.py' not in cmd:continue
        s=server_from(cmd,pid)
        if not s or not (s.parent/'index.html').exists():continue
        try:txt=s.read_text('utf-8',errors='ignore')
        except:continue
        if 'V5_PRODUCT_CATALOG' not in txt or s.stat().st_size<50000:continue
        p=port(pid)
        if p is None:continue
        vm=re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)',txt)
        ver=vm.group(1) if vm else 'unknown'
        rows.append((s.stat().st_mtime,pid,cmd,s,ver,p))
    if not rows:return None
    rows.sort(reverse=True)
    return rows[0]

print('\nYMS CRM UI REPAIR\n=================')
f=find_running()
if not f:raise SystemExit('\nCould not find a running full YMS V5 app. Open YMS first, then rerun this command.')
_,pid,cmd,server,ver,old_port=f
app=server.parent;index=app/'index.html'
print('Found YMS',ver,'at',app)

html=index.read_text('utf-8',errors='ignore')
backup=app/f'index.html.before-crm-repair-{time.strftime("%Y%m%d-%H%M%S")}'
backup.write_text(html,encoding='utf-8')
print('Backup:',backup.name)

print('Downloading CRM UI files from your GitHub repo...')
js=fetch(JS_URL);css=fetch(CSS_URL)
if 'v506CrmNav' not in js or 'v506BulkBar' not in js:raise SystemExit('CRM JS validation failed; original YMS left unchanged.')

# Strengthen the nav lookup for the branded/responsive V5 header.
old="function findNavButton(label){return [...document.querySelectorAll('button,a,[role=\"tab\"]')].find(e=>(e.textContent||'').trim().replace(/\\s+\\d+$/,'').toLowerCase()===label.toLowerCase())}"
new="function findNavButton(label){const q=String(label||'').toLowerCase();const els=[...document.querySelectorAll('button,a,[role=\"tab\"],[onclick],[data-tab],[data-view]')];return els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('href'),e.getAttribute('data-tab'),e.getAttribute('data-view'),e.id].filter(Boolean).join(' ').toLowerCase();return s.includes(q)})}"
if old in js:js=js.replace(old,new,1)

# Replace any earlier CRM hotfix block, then add one clean inline copy just before body end.
start='<!-- YMS CRM DIRECT REPAIR START -->';end='<!-- YMS CRM DIRECT REPAIR END -->'
html=re.sub(re.escape(start)+r'.*?'+re.escape(end),'',html,flags=re.S)
block=start+'\n<style>\n'+css+'\n</style>\n<script>\n'+js+'\n</script>\n'+end
if '</body>' in html:html=html.replace('</body>',block+'\n</body>',1)
else:html+='\n'+block

if 'YMS CRM DIRECT REPAIR START' not in html or 'v506CrmNav' not in html:
    raise SystemExit('Repair validation failed before write; original YMS left unchanged.')
index.write_text(html,encoding='utf-8')
print('CRM UI written. Restarting the same YMS instance...')

try:os.kill(pid,signal.SIGTERM)
except ProcessLookupError:pass
for _ in range(30):
    try:os.kill(pid,0);time.sleep(.1)
    except ProcessLookupError:break

try:
    parts=shlex.split(cmd);py=parts[0] if parts and 'python' in Path(parts[0]).name.lower() else sys.executable
except:py=sys.executable
log=app/'YMS_CRM_UI_REPAIR.log'
lf=open(log,'w',encoding='utf-8')
proc=subprocess.Popen([py,str(server)],cwd=str(app),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
new_port=None
for _ in range(80):
    time.sleep(.15)
    if proc.poll() is not None:break
    new_port=port(proc.pid)
    if new_port:break
if proc.poll() is not None or not new_port:
    index.write_text(backup.read_text('utf-8'),encoding='utf-8')
    try:subprocess.Popen([py,str(server)],cwd=str(app),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except:pass
    tail=''
    try:tail=log.read_text('utf-8',errors='ignore')[-4000:]
    except:pass
    raise SystemExit('\nRepair rolled back safely. Error:\n'+tail)

url=f'http://127.0.0.1:{new_port}/?crmrepair={int(time.time())}'
print('\nSUCCESS — CRM UI repaired.')
print('Opening',url)
subprocess.Popen(['open',url])
print('\nYou should now see CRM in the top navigation and Bulk CRM / Emailed in Prospects.')
