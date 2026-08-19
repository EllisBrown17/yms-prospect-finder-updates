#!/usr/bin/env python3
"""YMS Prospect Finder 5.0.2 — Intelligence Workspace UX + expanded ALFRA range."""
from pathlib import Path
import os,re,sys,time,subprocess,py_compile

TARGET_VERSION="5.0.2"
APP_DIR=Path(__file__).resolve().parent
if sys.platform=="darwin":
    DATA_DIR=Path.home()/"Library"/"Application Support"/"YMS Prospect Finder V3"
elif os.name=="nt":
    DATA_DIR=Path(os.getenv("APPDATA",Path.home()))/"YMS Prospect Finder V3"
else:
    DATA_DIR=Path.home()/".yms_prospect_finder_v3"
BACKUPS=DATA_DIR/"update-backups"

PUBLIC_FUNC='''def v5_product_catalog_public():
    out=[]
    for pid,p in V5_PRODUCT_CATALOG.items():
        out.append({
            "id":pid,"name":p["name"],"division":p.get("division","Other"),"category":p["category"],
            "verification":"VERIFIED PRODUCT FACT","verified_fact":p["verified_fact"],"verified_details":p.get("verified_details",[]),
            "source_label":p.get("source_label"),"source_url":p.get("source_url"),"simple":p["simple"],"workflow":p["workflow"],
            "validation_questions":p["questions"],"likely_roles":p["roles"],"unknowns":p["unknowns"],"do_not_claim":p["do_not_claim"],
            "related":p.get("related",[]),"models":p.get("models",[]),"range_note":p.get("range_note","")
        })
    order={"Control cabinet":0,"Steel & metal":1,"Magnet & lifting":2,"Other":9}
    out.sort(key=lambda x:(order.get(x.get("division"),9),x.get("category",""),x.get("name","")))
    return out


'''

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
                try:rows.append((p.stat().st_mtime,p))
                except Exception:pass
    if not rows:fail("5.0.2 could not find the safe pre-update backup. No prospect data was changed.")
    return max(rows,key=lambda x:x[0])[1]

def companion(name):
    p=APP_DIR/name
    if not p.exists():fail("5.0.2 package is incomplete: missing "+name)
    return p.read_text("utf-8")

def patch_server(src,range_insert):
    s=re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']','APP_VERSION = "5.0.2"',src,count=1)
    if 'APP_VERSION = "5.0.2"' not in s:fail("5.0.2 could not update the app version safely.")
    marker="def v5_product_catalog_public():\n"
    if marker not in s:fail("5.0.2 could not locate the V5 product catalog. Nothing was changed.")
    if "# V5.0.2 expanded ALFRA product-family intelligence." not in s:
        s=s.replace(marker,range_insert+"\n\n"+marker,1)
    a=s.find(marker);b=s.find("def v5_product_leads(",a)
    if a<0 or b<0:fail("5.0.2 could not safely extend the public product catalog.")
    s=s[:a]+PUBLIC_FUNC+s[b:]
    return s

def patch_html(src,css,js):
    s=src
    if "V5.0.2 intelligence workspace UX */" not in s:
        pos=s.rfind("</style>")
        if pos<0:fail("5.0.2 could not locate the stylesheet.")
        s=s[:pos]+"\n"+css+"\n"+s[pos:]
    if "V5.0.2 intelligence workspace UX overrides" not in s:
        pos=s.rfind("</script>")
        if pos<0:fail("5.0.2 could not locate the application script.")
        s=s[:pos]+"\n"+js+"\n"+s[pos:]
    s=re.sub(r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>','<title>YMS Prospect Finder V5.0.2 — YMS-Tools</title>',s,count=1)
    s=re.sub(r'<b id="versionLabel">Prospect Finder V[^<]+</b>','<b id="versionLabel">Prospect Finder V5.0.2 Mac</b>',s,count=1)
    s=s.replace("Start with an ALFRA product. Find the companies that can actually use it.","Browse the ALFRA range. Turn products into qualified sales opportunities.",1)
    s=s.replace("One sales queue. Every email and outcome remembered.","Your outreach command centre. Work the right email next.",1)
    return s

def main():
    backup=safe_backup()
    try:
        css=companion("v502_ui.css");js=companion("v502_ui.js");range_insert=companion("v502_range.py.txt")
        current_server=(backup/"server.py").read_text("utf-8")
        current_html=(backup/"index.html").read_text("utf-8")
        if "V5_PRODUCT_CATALOG" not in current_server or 'id="products"' not in current_html or 'id="outreach"' not in current_html:
            fail("5.0.2 requires a working V5 build. Nothing was changed.")
        new_server=patch_server(current_server,range_insert)
        new_html=patch_html(current_html,css,js)
        tmp=APP_DIR/"server.py.5.0.2-new";tmp.write_text(new_server,encoding="utf-8");py_compile.compile(str(tmp),doraise=True)
        htmp=APP_DIR/"index.html.5.0.2-new";htmp.write_text(new_html,encoding="utf-8")
        if len(re.findall(r'id="products"',new_html))!=1 or len(re.findall(r'id="outreach"',new_html))!=1:
            fail("5.0.2 interface validation failed before install.")
        if "v502ActionStages" not in new_html or "bs160" not in new_server or "chip_removal" not in new_server:
            fail("5.0.2 intelligence validation failed before install.")
        os.replace(tmp,APP_DIR/"server.py");os.replace(htmp,APP_DIR/"index.html")
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        (DATA_DIR/"last_ota_update.txt").write_text("5.0.2\n"+time.strftime("%Y-%m-%d %H:%M:%S")+"\nIntelligence workspace UX + expanded ALFRA range\n",encoding="utf-8")
        helper=DATA_DIR/"launcher_refresh.py"
        if sys.platform=="darwin" and helper.exists():
            try:subprocess.run([sys.executable,str(helper),str(APP_DIR),str(DATA_DIR),str(sys.executable)],timeout=20,capture_output=True)
            except Exception:pass
    except SystemExit:raise
    except Exception as ex:fail("5.0.2 install failed safely: "+str(ex))
    os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])

if __name__=="__main__":main()
