#!/usr/bin/env python3
"""YMS Prospect Finder 5.0.4 — CRM + smart follow-up OTA."""
from pathlib import Path
import os,re,sys,time,subprocess,py_compile

TARGET_VERSION="5.0.4"
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
    except Exception:
        pass
    raise SystemExit(str(msg))

def safe_backup():
    rows=[]
    if BACKUPS.exists():
        for p in BACKUPS.glob("before-"+TARGET_VERSION+"-*"):
            if (p/"server.py").exists() and (p/"index.html").exists():
                try: rows.append((p.stat().st_mtime,p))
                except Exception: pass
    if not rows:
        fail("5.0.4 could not find the safe pre-update backup. No prospect or CRM data was changed.")
    return max(rows,key=lambda x:x[0])[1]

def companion(name):
    p=APP_DIR/name
    if not p.exists(): fail("5.0.4 package is incomplete: missing "+name)
    return p.read_text("utf-8")

def patch_server(src):
    s,n=re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "5.0.4"',src,count=1)
    if n!=1 and 'APP_VERSION = "5.0.4"' not in s:
        fail("5.0.4 could not update the app version safely.")
    return s

def patch_html(src,css,js):
    s=src
    platform="Mac" if sys.platform=="darwin" else ("Windows" if os.name=="nt" else "Desktop")
    if "V5.0.4 CRM + smart follow-up */" not in s:
        pos=s.rfind("</style>")
        if pos<0: fail("5.0.4 could not locate the stylesheet.")
        s=s[:pos]+"\n"+css+"\n"+s[pos:]
    if "V5.0.4 CRM + smart follow-up layer" not in s:
        pos=s.rfind("</script>")
        if pos<0: fail("5.0.4 could not locate the application script.")
        s=s[:pos]+"\n"+js+"\n"+s[pos:]
    s=re.sub(r'<title>YMS Prospect Finder V[^<]+</title>',f'<title>YMS Prospect Finder V5.0.4 {platform} — YMS-Tools</title>',s,count=1)
    s=re.sub(r'<b id="versionLabel">[^<]*</b>','<b id="versionLabel">V5.0.4</b>',s,count=1)
    return s

def main():
    backup=safe_backup()
    try:
        css=companion("v504_crm.css")
        js=companion("v504_crm.js")
        current_server=(backup/"server.py").read_text("utf-8")
        current_html=(backup/"index.html").read_text("utf-8")

        if "V5_PRODUCT_CATALOG" not in current_server or 'id="outreach"' not in current_html:
            fail("5.0.4 requires a working YMS V5 build. Nothing was changed.")
        if "v502ActionStages" not in current_html:
            fail("5.0.4 requires the current Outreach intelligence workspace. Nothing was changed.")

        new_server=patch_server(current_server)
        new_html=patch_html(current_html,css,js)

        if "v504CrmDashboard" not in new_html or "v504EnableCrmNotifications" not in new_html or "Email sent" not in new_html:
            fail("5.0.4 CRM validation failed before install.")

        tmp=APP_DIR/"server.py.5.0.4-new"
        tmp.write_text(new_server,encoding="utf-8")
        py_compile.compile(str(tmp),doraise=True)
        htmp=APP_DIR/"index.html.5.0.4-new"
        htmp.write_text(new_html,encoding="utf-8")

        os.replace(tmp,APP_DIR/"server.py")
        os.replace(htmp,APP_DIR/"index.html")
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"last_ota_update.txt").write_text(
            "5.0.4\n"+time.strftime("%Y-%m-%d %H:%M:%S")+
            "\nCRM + smart follow-up reminders\n",encoding="utf-8"
        )

        helper=DATA_DIR/"launcher_refresh.py"
        if sys.platform=="darwin" and helper.exists():
            try:
                subprocess.run([sys.executable,str(helper),str(APP_DIR),str(DATA_DIR),str(sys.executable)],timeout=20,capture_output=True)
            except Exception: pass
    except SystemExit:
        raise
    except Exception as ex:
        fail("5.0.4 install failed safely: "+str(ex))

    os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])

if __name__=="__main__": main()
