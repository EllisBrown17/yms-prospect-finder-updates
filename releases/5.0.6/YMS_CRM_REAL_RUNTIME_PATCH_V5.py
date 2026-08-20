#!/usr/bin/env python3
from pathlib import Path
import os,re,subprocess,sys,time,urllib.request,shutil

# Patch the actual Mac runtime in-place. Do NOT rebuild or replace the backend.
ASSET_COMMIT='10e6f10a7ecbfe8048fc301d92527d80b7f3d1ed'
BASE=f'https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/{ASSET_COMMIT}/releases/5.0.6/'
JS_URL=BASE+'v506_crm.js'
CSS_URL=BASE+'v506_crm.css'
HOME=Path.home()
DATA=HOME/'Library'/'Application Support'/'YMS Prospect Finder V3'
APP=HOME/'Downloads'/'YMS_Prospect_Finder_V4_1_0_OTA_UPDATER_MAC'
SERVER=APP/'server.py'
INDEX=APP/'index.html'
HELPER=DATA/'launcher_refresh.py'
RUNTIME_PTR=DATA/'runtime_path.txt'
PY_PTR=DATA/'runtime_python.txt'
DESKTOP_APP=HOME/'Desktop'/'YMS Prospect Finder.app'
PORT=8765


def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={
        'User-Agent':'YMS-CRM-Real-Runtime-Patch/5',
        'Cache-Control':'no-cache','Pragma':'no-cache'
    })
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode('utf-8')


def get_version(text):
    m=re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)',text)
    return m.group(1) if m else 'unknown'


def strengthen_crm_js(js):
    start=js.find('function findNavButton(label)')
    end=js.find('function ensureCrmNav', start if start>=0 else 0)
    if start<0 or end<0 or end<=start:
        raise RuntimeError('Could not locate CRM navigation helper in verified 5.0.6 JS.')
    replacement='''function findNavButton(label){\n    const q=String(label||'').toLowerCase();\n    const els=[...document.querySelectorAll('button,a,[role="tab"],[onclick],[data-tab],[data-view]')];\n    const exact=els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('href'),e.getAttribute('data-tab'),e.getAttribute('data-view'),e.id].filter(Boolean).join(' ').toLowerCase();return s.includes(q)});\n    if(exact)return exact;\n    return els.find(e=>{const s=[e.textContent,e.getAttribute('onclick'),e.getAttribute('data-tab'),e.getAttribute('data-view'),e.id].filter(Boolean).join(' ').toLowerCase();return /outreach|prospect|product|discover|dashboard|settings/.test(s)});\n  }\n  '''
    return js[:start]+replacement+js[end:]


def choose_python():
    # Preserve the interpreter already recorded by the working YMS launcher if valid.
    if PY_PTR.exists():
        try:
            p=Path(PY_PTR.read_text('utf-8',errors='ignore').strip()).expanduser()
            if p.exists() and os.access(p,os.X_OK):
                return str(p)
        except Exception:
            pass
    for p in ['/opt/homebrew/bin/python3','/usr/local/bin/python3','/usr/bin/python3',sys.executable]:
        if p and Path(p).exists() and os.access(p,os.X_OK):
            return p
    raise RuntimeError('No working Python interpreter was found.')


def http_ok(expect_patch=False):
    try:
        req=urllib.request.Request(f'http://127.0.0.1:{PORT}/?crmprobe={int(time.time())}',headers={'Cache-Control':'no-cache','Pragma':'no-cache'})
        with urllib.request.urlopen(req,timeout=2) as r:
            body=r.read().decode('utf-8',errors='ignore')
        if expect_patch:
            return 'YMS CRM REAL RUNTIME PATCH V5 START' in body and 'v506CrmNav' in body and 'v506BulkBar' in body
        return True
    except Exception:
        return False


print('\nYMS 5.0.6 CRM REAL RUNTIME PATCH V5')
print('===================================\n')

if not SERVER.exists() or not INDEX.exists():
    raise SystemExit('The actual YMS runtime folder is missing server.py or index.html. Nothing was changed.')
server_text=SERVER.read_text('utf-8',errors='ignore')
version=get_version(server_text)
print('Runtime:',APP)
print('Backend version:',version)
print('Backend size:',SERVER.stat().st_size,'bytes')
if version!='5.0.6' or SERVER.stat().st_size<200000 or 'V5_PRODUCT_CATALOG' not in server_text:
    raise SystemExit('This is not the verified full 5.0.6 runtime. Nothing was changed.')

html=INDEX.read_text('utf-8',errors='ignore')
if 'id="prospects"' not in html or 'id="outreach"' not in html:
    raise SystemExit('The real runtime UI baseline is not recognised. Nothing was changed.')
if 'markOutreachSent' not in html or 'openOutreachFor' not in html:
    raise SystemExit('The outreach foundation required by CRM is missing. Nothing was changed.')

print('1/4 Backing up the real runtime UI...')
stamp=time.strftime('%Y%m%d-%H%M%S')
backup=APP/f'index.html.before-real-crm-v5-{stamp}'
shutil.copy2(INDEX,backup)
print('Backup:',backup.name)

print('2/4 Injecting CRM into the real 5.0.6 runtime...')
js=strengthen_crm_js(fetch(JS_URL))
css=fetch(CSS_URL)
if 'v506CrmNav' not in js or 'v506BulkBar' not in js:
    raise SystemExit('Verified CRM assets failed validation. Original UI is still backed up.')

# Remove previous repair blocks only; leave normal YMS code untouched.
patterns=[
    r'<!-- YMS CRM DIRECT REPAIR START -->.*?<!-- YMS CRM DIRECT REPAIR END -->',
    r'<!-- YMS CRM CANONICAL 5\.0\.6(?: V\d+)? START -->.*?<!-- YMS CRM CANONICAL 5\.0\.6(?: V\d+)? END -->',
    r'<!-- YMS CRM REAL RUNTIME PATCH V5 START -->.*?<!-- YMS CRM REAL RUNTIME PATCH V5 END -->'
]
for pat in patterns:
    html=re.sub(pat,'',html,flags=re.S)
start='<!-- YMS CRM REAL RUNTIME PATCH V5 START -->'
end='<!-- YMS CRM REAL RUNTIME PATCH V5 END -->'
block=start+'\n<style id="yms-v506-crm-style">\n'+css+'\n</style>\n<script id="yms-v506-crm-script">\n'+js+'\n</script>\n'+end
if '</body>' in html:
    html=html.replace('</body>',block+'\n</body>',1)
else:
    html+='\n'+block+'\n'
if start not in html or 'v506CrmNav' not in html or 'v506BulkBar' not in html:
    raise SystemExit('CRM injection validation failed before write.')
INDEX.write_text(html,encoding='utf-8')
print('CRM UI written to the actual runtime.')

print('3/4 Restoring the launcher pointers to the actual runtime...')
DATA.mkdir(parents=True,exist_ok=True)
py=choose_python()
RUNTIME_PTR.write_text(str(APP),encoding='utf-8')
PY_PTR.write_text(py,encoding='utf-8')
print('runtime_path.txt ->',APP)
print('runtime_python.txt ->',py)

# Rebuild the Desktop launcher using the app's own helper. This is how YMS is designed to launch.
if HELPER.exists():
    try:
        r=subprocess.run([py,str(HELPER),str(APP),str(DATA),py],timeout=30,capture_output=True,text=True)
        if r.returncode!=0:
            print('Launcher helper returned',r.returncode)
            if r.stderr.strip(): print(r.stderr.strip())
    except Exception as ex:
        print('Launcher refresh warning:',ex)
else:
    print('Launcher helper is missing; existing Desktop launcher will be used if present.')

print('4/4 Opening YMS through its real launcher...')
# If YMS is already alive, SimpleHTTPRequestHandler will serve the changed index.html on refresh.
# If it is down, the Desktop .app will start it using runtime_python.txt and runtime_path.txt.
if DESKTOP_APP.exists():
    subprocess.Popen(['/usr/bin/open',str(DESKTOP_APP)])
else:
    # Fallback uses the exact same interpreter/runtime pointers, not this repair script's Python.
    log=HOME/'Library'/'Logs'/'YMS Prospect Finder.log'
    log.parent.mkdir(parents=True,exist_ok=True)
    lf=open(log,'a',encoding='utf-8')
    subprocess.Popen([py,str(SERVER)],cwd=str(APP),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)

# Give the launcher time to start if needed, then verify the actual page served on port 8765.
verified=False
for _ in range(50):
    time.sleep(.3)
    if http_ok(expect_patch=True):
        verified=True
        break

if not verified:
    # Do not roll the UI back: the patch itself is valid and may only need the normal launcher reopened.
    print('\nCRM was patched successfully, but YMS is not yet serving the patched page on port 8765.')
    print('Open the Desktop "YMS Prospect Finder" app once. If it still fails, send the last 30 lines of:')
    print('~/Library/Logs/YMS Prospect Finder.log')
    raise SystemExit(2)

url=f'http://127.0.0.1:{PORT}/?crm=5'
subprocess.Popen(['/usr/bin/open',url])
print('\nSUCCESS — the real YMS 5.0.6 runtime is serving the CRM patch.')
print('Expected UI: CRM tab in navigation + Bulk CRM / Emailed controls in Prospects.')
print('No prospect/settings database files were modified by this patch.')
