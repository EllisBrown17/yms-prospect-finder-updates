#!/usr/bin/env python3
"""YMS Prospect Finder 5.0.1 — Product/Outreach navigation syntax hotfix."""
from pathlib import Path
import os,re,sys,time,subprocess,py_compile

TARGET_VERSION="5.0.1"
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
        fail("5.0.1 could not find the safe pre-update backup. No prospect data was changed.")
    return max(rows,key=lambda x:x[0])[1]


def patch_server(src):
    s=re.sub(r'APP_VERSION\s*=\s*"[^"]+"','APP_VERSION = "5.0.1"',src,count=1)
    if s==src and 'APP_VERSION = "5.0.1"' not in s:
        s=re.sub(r"APP_VERSION\s*=\s*'[^']+'",'APP_VERSION = "5.0.1"',src,count=1)
    return s


def patch_html(src):
    s=src
    # Exact 5.0.0 defect: the two NEW inline navigation handlers were created
    # by a raw regex replacement containing escaped single quotes. Those
    # backslashes survive into HTML and Safari compiles the handler as e.g.
    # show(\'products\',this), which raises "Invalid escape in identifier".
    # The V5 <script> block itself parses successfully; do not rewrite it.
    bad_products = r'''onclick="show(\'products\',this)"'''
    bad_outreach = r'''onclick="show(\'outreach\',this)"'''
    good_products = '''onclick="show('products',this)"'''
    good_outreach = '''onclick="show('outreach',this)"'''

    found_products=s.count(bad_products)
    found_outreach=s.count(bad_outreach)
    if found_products!=1 or found_outreach!=1:
        fail(
            "5.0.1 could not uniquely identify both broken 5.0.0 navigation handlers "
            f"(Products={found_products}, Outreach={found_outreach}). No files were replaced."
        )

    s=s.replace(bad_products,good_products,1)
    s=s.replace(bad_outreach,good_outreach,1)
    if bad_products in s or bad_outreach in s:
        fail("5.0.1 could not fully repair the Product/Outreach navigation handlers.")

    s=re.sub(r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>','<title>YMS Prospect Finder V5.0.1 — YMS-Tools</title>',s,count=1)
    s=re.sub(r'<b id="versionLabel">Prospect Finder V[^<]+</b>','<b id="versionLabel">Prospect Finder V5.0.1</b>',s,count=1)
    return s,found_products+found_outreach


def main():
    backup=safe_backup()
    try:
        current_server=(backup/"server.py").read_text("utf-8")
        current_html=(backup/"index.html").read_text("utf-8")
        new_server=patch_server(current_server)
        new_html,repaired_count=patch_html(current_html)

        tmp=APP_DIR/"server.py.5.0.1-new"
        tmp.write_text(new_server,encoding="utf-8")
        py_compile.compile(str(tmp),doraise=True)
        html_tmp=APP_DIR/"index.html.5.0.1-new"
        html_tmp.write_text(new_html,encoding="utf-8")

        os.replace(tmp,APP_DIR/"server.py")
        os.replace(html_tmp,APP_DIR/"index.html")
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"last_ota_update.txt").write_text(
            "5.0.1\n"+time.strftime("%Y-%m-%d %H:%M:%S")+
            f"\nProduct/Outreach Safari navigation hotfix — repaired {repaired_count} inline handlers\n",
            encoding="utf-8"
        )

        # Preserve the 4.2.11 rule: every OTA refreshes the Desktop launcher/icon.
        helper=DATA_DIR/"launcher_refresh.py"
        if sys.platform=="darwin" and helper.exists():
            try:
                subprocess.run([sys.executable,str(helper),str(APP_DIR),str(DATA_DIR),str(sys.executable)],timeout=20,capture_output=True)
            except Exception:
                pass
    except Exception as ex:
        fail("5.0.1 install failed safely: "+str(ex))

    os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])


if __name__=="__main__":
    main()
