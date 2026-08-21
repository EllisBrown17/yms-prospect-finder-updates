#!/usr/bin/env python3
from pathlib import Path
import os, signal, subprocess, sys, time, urllib.request

SOURCE_COMMIT='3d0384eacd88f4cbe06009f7df80b095010eb12d'
SOURCE_URL=f'https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/{SOURCE_COMMIT}/releases/5.1.0/YMS_EFFICIENCY_OS_5_1.py'


def fetch(url):
    req=urllib.request.Request(url+'?t='+str(int(time.time())),headers={'User-Agent':'YMS-Efficiency-5.1.1','Cache-Control':'no-cache','Pragma':'no-cache'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode('utf-8')

print('\nYMS EFFICIENCY OS 5.1.1')
print('=========================\n')
print('Loading the verified 5.1 interface and replacing the faulty restart/verification step...')
source=fetch(SOURCE_URL)
start=source.find("print('4/4 Verifying the page YMS actually serves...')")
end=source.find("url=f'http://127.0.0.1:{PORT}/?efficiency=51&ts={int(time.time())}'",start)
if start<0 or end<0:
    raise SystemExit('Could not locate the 5.1 verification block. Nothing was changed.')

replacement=r'''print('4/4 Restarting the exact YMS runtime and verifying it...')

def _listener_pid():
    try:
        out=subprocess.check_output(['lsof','-nP','-iTCP:'+str(PORT),'-sTCP:LISTEN','-t'],text=True,stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            line=line.strip()
            if line.isdigit(): return int(line)
    except Exception: pass
    return None

def _pid_command(pid):
    try:
        return subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True,stderr=subprocess.DEVNULL).strip()
    except Exception: return ''

def _stop_existing_yms():
    pid=_listener_pid()
    if not pid: return
    cmd=_pid_command(pid)
    # Never kill an unrelated service occupying the YMS port.
    if 'server.py' not in cmd and 'YMS' not in cmd:
        INDEX.write_text((backup_dir/'index.html').read_text('utf-8',errors='ignore'),encoding='utf-8')
        raise SystemExit('Port 8765 is occupied by a non-YMS process, so nothing was restarted and the old UI was restored.')
    try: os.kill(pid,__import__('signal').SIGTERM)
    except ProcessLookupError: return
    deadline=time.time()+5
    while time.time()<deadline:
        if _listener_pid()!=pid: return
        time.sleep(.15)
    try: os.kill(pid,__import__('signal').SIGKILL)
    except ProcessLookupError: pass
    time.sleep(.35)

_stop_existing_yms()
log=HOME/'Library'/'Logs'/'YMS Prospect Finder.log'
log.parent.mkdir(parents=True,exist_ok=True)
lf=open(log,'a',encoding='utf-8')
lf.write('\n--- Efficiency OS 5.1.1 restart '+time.strftime('%Y-%m-%d %H:%M:%S')+' ---\n');lf.flush()
proc=subprocess.Popen([py,str(SERVER)],cwd=str(APP),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)

verified=False
for _ in range(80):
    if proc.poll() is not None: break
    if page_contains_marker():
        verified=True
        break
    time.sleep(.25)

if not verified:
    INDEX.write_text((backup_dir/'index.html').read_text('utf-8',errors='ignore'),encoding='utf-8')
    # Restore the old UI and restart the same runtime once so YMS is usable.
    try:
        if proc.poll() is None: proc.terminate()
    except Exception: pass
    time.sleep(.4)
    try: subprocess.Popen([py,str(SERVER)],cwd=str(APP),stdout=lf,stderr=subprocess.STDOUT,start_new_session=True)
    except Exception: pass
    tail=''
    try:
        lf.flush(); tail=log.read_text('utf-8',errors='ignore')[-5000:]
    except Exception: pass
    raise SystemExit('Efficiency interface still did not verify after a clean YMS restart. The old UI was restored.\n\nStartup log:\n'+(tail or '[log empty]'))

print('Verified: the restarted YMS process is serving Efficiency OS from the exact runtime.')
'''

patched=source[:start]+replacement+source[end:]
patched=patched.replace("print('\\nYMS EFFICIENCY OS 5.1')","print('\\nYMS EFFICIENCY OS 5.1.1')",1)
patched=patched.replace("SUCCESS — Efficiency OS is live.","SUCCESS — Efficiency OS 5.1.1 is live.",1)
patched=patched.replace("?efficiency=51&ts=","?efficiency=511&ts=",1)

compile(patched,'YMS_EFFICIENCY_OS_5_1_1_runtime.py','exec')
ns={'__name__':'__main__','__file__':'/tmp/YMS_EFFICIENCY_OS_5_1_1_runtime.py'}
exec(compile(patched,ns['__file__'],'exec'),ns,ns)
