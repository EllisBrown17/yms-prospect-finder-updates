#!/usr/bin/env python3
"""YMS Prospect Finder 5.0.6 — separate CRM workspace + bulk Emailed OTA."""
from pathlib import Path
import os,re,sys,time,subprocess,py_compile

TARGET_VERSION="5.0.6"
APP_DIR=Path(__file__).resolve().parent
if sys.platform=="darwin":
    DATA_DIR=Path.home()/"Library"/"Application Support"/"YMS Prospect Finder V3"
elif os.name=="nt":
    DATA_DIR=Path(os.getenv("APPDATA",Path.home()))/"YMS Prospect Finder V3"
else:
    DATA_DIR=Path.home()/".yms_prospect_finder_v3"
BACKUPS=DATA_DIR/"update-backups"

def fail(msg):
    try:
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"update_restart_error.txt").write_text(str(msg),encoding="utf-8")
    except Exception: pass
    raise SystemExit(str(msg))

def safe_backup():
    rows=[]
    if BACKUPS.exists():
        for p in BACKUPS.glob("before-"+TARGET_VERSION+"-*"):
            if (p/"server.py").exists() and (p/"index.html").exists():
                try: rows.append((p.stat().st_mtime,p))
                except Exception: pass
    if not rows: fail("5.0.6 could not find the safe pre-update backup. No prospect or CRM data was changed.")
    return max(rows,key=lambda x:x[0])[1]

def companion(name):
    p=APP_DIR/name
    if not p.exists(): fail("5.0.6 package is incomplete: missing "+name)
    return p.read_text("utf-8")

def patch_server(src):
    s,n=re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "5.0.6"',src,count=1)
    if n!=1 and 'APP_VERSION = "5.0.6"' not in s: fail("5.0.6 could not update the app version safely.")
    return s

def inject_before(s,needle,payload,marker):
    if marker in s: return s
    pos=s.rfind(needle)
    if pos<0: fail("5.0.6 could not locate "+needle+" in the application UI.")
    return s[:pos]+"\n"+payload+"\n"+s[pos:]

def patch_html(src,crm504_css,crm504_js,crm506_css,crm506_js):
    s=src
    platform="Mac" if sys.platform=="darwin" else ("Windows" if os.name=="nt" else "Desktop")
    s=inject_before(s,"</style>",crm504_css,"V5.0.4 CRM + smart follow-up */")
    s=inject_before(s,"</script>",crm504_js,"V5.0.4 CRM + smart follow-up layer")
    s=inject_before(s,"</style>",crm506_css,"V5.0.6 separate CRM workspace + bulk emailed */")
    s=inject_before(s,"</script>",crm506_js,"V5.0.6 separate CRM workspace + bulk Emailed action")
    s=re.sub(r'<title>YMS Prospect Finder V[^<]+</title>',f'<title>YMS Prospect Finder V5.0.6 {platform} — YMS-Tools</title>',s,count=1)
    s=re.sub(r'<b id="versionLabel">[^<]*</b>','<b id="versionLabel">V5.0.6</b>',s,count=1)
    return s

def main():
    backup=safe_backup()
    try:
        current_server=(backup/"server.py").read_text("utf-8")
        current_html=(backup/"index.html").read_text("utf-8")
        if "V5_PRODUCT_CATALOG" not in current_server or 'id="prospects"' not in current_html or 'id="outreach"' not in current_html:
            fail("5.0.6 requires a working YMS V5 build. Nothing was changed.")
        if "v502ActionStages" not in current_html:
            fail("5.0.6 requires the current YMS Outreach workspace. Nothing was changed.")
        new_server=patch_server(current_server)
        new_html=patch_html(current_html,companion("v504_crm.css"),companion("v504_crm.js"),companion("v506_crm.css"),companion("v506_crm.js"))
        required=["v506CrmNav","v506BulkBar","v506BulkEmailed","V5.0.6 separate CRM workspace + bulk emailed */","v504CrmDashboard"]
        if any(x not in new_html for x in required): fail("5.0.6 CRM validation failed before install.")
        tmp=APP_DIR/"server.py.5.0.6-new";tmp.write_text(new_server,encoding="utf-8");py_compile.compile(str(tmp),doraise=True)
        htmp=APP_DIR/"index.html.5.0.6-new";htmp.write_text(new_html,encoding="utf-8")
        os.replace(tmp,APP_DIR/"server.py");os.replace(htmp,APP_DIR/"index.html")
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"last_ota_update.txt").write_text("5.0.6\n"+time.strftime("%Y-%m-%d %H:%M:%S")+"\nSeparate CRM workspace + bulk Emailed action\n",encoding="utf-8")
        helper=DATA_DIR/"launcher_refresh.py"
        if sys.platform=="darwin" and helper.exists():
            try: subprocess.run([sys.executable,str(helper),str(APP_DIR),str(DATA_DIR),str(sys.executable)],timeout=20,capture_output=True)
            except Exception: pass
    except SystemExit: raise
    except Exception as ex: fail("5.0.6 install failed safely: "+str(ex))
    os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])

if __name__=="__main__": main()
