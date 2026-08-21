#!/usr/bin/env python3
from pathlib import Path
import base64,gzip,os,re,shutil,subprocess,sys,time,urllib.request

HOME=Path.home()
DATA=HOME/'Library'/'Application Support'/'YMS Prospect Finder V3'
PTR=DATA/'runtime_path.txt'
PYPTR=DATA/'runtime_python.txt'
FALLBACK=HOME/'Downloads'/'YMS_Prospect_Finder_V4_1_0_OTA_UPDATER_MAC'
DESKTOP_APP=HOME/'Desktop'/'YMS Prospect Finder.app'
PORT=8765
JS_GZ_B64='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'
CSS_GZ_B64='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'
START='<!-- YMS EFFICIENCY OS 5.1 START -->'
END='<!-- YMS EFFICIENCY OS 5.1 END -->'

def unpack(s):
    return gzip.decompress(base64.b64decode(s)).decode('utf-8')

def runtime_dir():
    if PTR.exists():
        try:
            p=Path(PTR.read_text('utf-8',errors='ignore').strip()).expanduser()
            if (p/'server.py').exists() and (p/'index.html').exists(): return p
        except Exception: pass
    return FALLBACK

def choose_python():
    if PYPTR.exists():
        try:
            p=Path(PYPTR.read_text('utf-8',errors='ignore').strip()).expanduser()
            if p.exists() and os.access(p,os.X_OK): return str(p)
        except Exception: pass
    for p in ['/opt/homebrew/bin/python3','/usr/local/bin/python3','/usr/bin/python3',sys.executable]:
        if p and Path(p).exists() and os.access(p,os.X_OK): return p
    return sys.executable

def page_contains_marker():
    try:
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}/?effprobe={int(time.time())}',headers={'Cache-Control':'no-cache','Pragma':'no-cache'})
        with urllib.request.urlopen(req,timeout=2) as r:
            body=r.read().decode('utf-8',errors='ignore')
        return START in body and '__YMS_EFFICIENCY_OS_510__' in body and 'v510Shell' in body
    except Exception:
        return False

def server_alive():
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/',timeout=1) as r:
            return 200 <= getattr(r,'status',200) < 500
    except Exception: return False

print('\nYMS EFFICIENCY OS 5.1')
print('=====================\n')
APP=runtime_dir();SERVER=APP/'server.py';INDEX=APP/'index.html'
print('Runtime:',APP)
if not SERVER.exists() or not INDEX.exists(): raise SystemExit('YMS runtime is missing server.py or index.html. Nothing changed.')
server=SERVER.read_text('utf-8',errors='ignore')
vm=re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)',server)
version=vm.group(1) if vm else 'unknown'
print('Backend:',version,'·',SERVER.stat().st_size,'bytes')
if SERVER.stat().st_size<200000 or 'V5_PRODUCT_CATALOG' not in server: raise SystemExit('This is not the full YMS V5 runtime. Nothing changed.')
html=INDEX.read_text('utf-8',errors='ignore')
if 'id="outreach"' not in html or 'id="discover"' not in html or 'id="products"' not in html: raise SystemExit('YMS UI baseline not recognised. Nothing changed.')

print('1/4 Backing up current UI...')
stamp=time.strftime('%Y%m%d-%H%M%S')
backup_dir=DATA/'update-backups'/f'before-5.1-efficiency-{stamp}'
backup_dir.mkdir(parents=True,exist_ok=True)
shutil.copy2(INDEX,backup_dir/'index.html')
(DATA/'efficiency_last_backup.txt').write_text(str(backup_dir),encoding='utf-8')
print('Backup:',backup_dir)

print('2/4 Installing efficiency-first interface...')
js=unpack(JS_GZ_B64);css=unpack(CSS_GZ_B64)
if '__YMS_EFFICIENCY_OS_510__' not in js or '#v510Shell' not in css: raise SystemExit('Embedded efficiency assets failed validation.')
html=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',html,flags=re.S)
block=START+'\n<style id="yms-efficiency-os-css">\n'+css+'\n</style>\n<script id="yms-efficiency-os-js">\n'+js+'\n</script>\n'+END
if '</body>' in html: html=html.replace('</body>',block+'\n</body>',1)
else: html+='\n'+block+'\n'
if START not in html or 'v510Shell' not in html or '__YMS_EFFICIENCY_OS_510__' not in html: raise SystemExit('Efficiency UI validation failed before write.')
INDEX.write_text(html,encoding='utf-8')
print('Installed: Today command centre · Finder · Work Queue · CRM · Products · Settings')

print('3/4 Restoring launcher pointers...')
DATA.mkdir(parents=True,exist_ok=True);PTR.write_text(str(APP),encoding='utf-8');py=choose_python();PYPTR.write_text(py,encoding='utf-8')
helper=DATA/'launcher_refresh.py'
if helper.exists():
    try: subprocess.run([py,str(helper),str(APP),str(DATA),py],timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception: pass

print('4/4 Verifying the page YMS actually serves...')
if not server_alive():
    if DESKTOP_APP.exists(): subprocess.Popen(['/usr/bin/open',str(DESKTOP_APP)])
    else:
        log=HOME/'Library'/'Logs'/'YMS Prospect Finder.log';log.parent.mkdir(parents=True,exist_ok=True);lf=open(log,'a',encoding='utf-8')
        subprocess.Popen([py,str(SERVER)],cwd=str(APP),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(40):
    if page_contains_marker(): break
    time.sleep(.25)
else:
    INDEX.write_text((backup_dir/'index.html').read_text('utf-8',errors='ignore'),encoding='utf-8')
    raise SystemExit('Efficiency interface did not verify on port 8765, so the old UI was restored automatically.')
url=f'http://127.0.0.1:{PORT}/?efficiency=51&ts={int(time.time())}'
subprocess.Popen(['/usr/bin/open',url])
print('\nSUCCESS — Efficiency OS is live.')
print('No prospect, API-key, scan or outreach database files were changed.')
print('Keyboard: 1 Today · 2 Finder · 3 Work · 4 CRM · 5 Products · 6 Settings · / Search')
