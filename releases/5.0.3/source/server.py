#!/usr/bin/env python3
"""YMS Prospect Finder 5.0.3 — YMS-Tools branding and responsive header OTA."""
from pathlib import Path
import os,re,sys,time,subprocess,py_compile

TARGET_VERSION="5.0.3"
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
                try:
                    rows.append((p.stat().st_mtime,p))
                except Exception:
                    pass
    if not rows:
        fail("5.0.3 could not find the safe pre-update backup. No prospect data was changed.")
    return max(rows,key=lambda x:x[0])[1]

def companion(name,encoding="utf-8"):
    p=APP_DIR/name
    if not p.exists():
        fail("5.0.3 package is incomplete: missing "+name)
    return p.read_text(encoding)

def brand_uri():
    raw="".join(companion("brand_image.b64","ascii").split())
    if len(raw)<1000 or not re.fullmatch(r"[A-Za-z0-9+/=]+",raw):
        fail("5.0.3 YMS brand image payload failed validation.")
    return "data:image/webp;base64,"+raw

def patch_server(src):
    s,n=re.subn(
        r'APP_VERSION\s*=\s*["\'][^"\']+["\']',
        'APP_VERSION = "5.0.3"',
        src,count=1
    )
    if n!=1 and 'APP_VERSION = "5.0.3"' not in s:
        fail("5.0.3 could not update the app version safely.")
    return s

def patch_html(src,css,js):
    s=src
    platform="Mac" if sys.platform=="darwin" else ("Windows" if os.name=="nt" else "Desktop")

    if "V5.0.3 branded header + responsive top UI */" not in s:
        pos=s.rfind("</style>")
        if pos<0:
            fail("5.0.3 could not locate the stylesheet.")
        s=s[:pos]+"\n"+css+"\n"+s[pos:]

    if "V5.0.3 branded header + responsive top UI */\n(function()" not in s:
        pos=s.rfind("</script>")
        if pos<0:
            fail("5.0.3 could not locate the application script.")
        s=s[:pos]+"\n"+js+"\n"+s[pos:]

    s=re.sub(
        r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>',
        f'<title>YMS Prospect Finder V5.0.3 {platform} — YMS-Tools</title>',
        s,count=1
    )
    s=re.sub(
        r'<b id="versionLabel">Prospect Finder V[^<]+</b>',
        '<b id="versionLabel">V5.0.3</b>',
        s,count=1
    )
    return s

def main():
    backup=safe_backup()
    try:
        css=companion("v503_header.css")
        js=companion("v503_header.js").replace("__YMS_BRAND_DATA_URI__",brand_uri())

        current_server=(backup/"server.py").read_text("utf-8")
        current_html=(backup/"index.html").read_text("utf-8")

        if "V5_PRODUCT_CATALOG" not in current_server or 'id="products"' not in current_html or 'id="outreach"' not in current_html:
            fail("5.0.3 requires a working V5 build. Nothing was changed.")

        new_server=patch_server(current_server)
        new_html=patch_html(current_html,css,js)

        # This branding/UI OTA is intentionally based on the current 5.0.2 intelligence workspace.
        if "V5.0.2 intelligence workspace UX */" not in new_html:
            fail("5.0.3 expected the 5.0.2 intelligence UI baseline. Nothing was changed.")
        if "v503Header" not in new_html or "data:image/webp;base64," not in new_html:
            fail("5.0.3 branding validation failed before install.")

        tmp=APP_DIR/"server.py.5.0.3-new"
        tmp.write_text(new_server,encoding="utf-8")
        py_compile.compile(str(tmp),doraise=True)

        htmp=APP_DIR/"index.html.5.0.3-new"
        htmp.write_text(new_html,encoding="utf-8")

        os.replace(tmp,APP_DIR/"server.py")
        os.replace(htmp,APP_DIR/"index.html")

        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"last_ota_update.txt").write_text(
            "5.0.3\n"+time.strftime("%Y-%m-%d %H:%M:%S")+
            "\nYMS-Tools branded header + responsive top UI\n",
            encoding="utf-8"
        )

        helper=DATA_DIR/"launcher_refresh.py"
        if sys.platform=="darwin" and helper.exists():
            try:
                subprocess.run(
                    [sys.executable,str(helper),str(APP_DIR),str(DATA_DIR),str(sys.executable)],
                    timeout=20,capture_output=True
                )
            except Exception:
                pass
    except SystemExit:
        raise
    except Exception as ex:
        fail("5.0.3 install failed safely: "+str(ex))

    os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])

if __name__=="__main__":
    main()
