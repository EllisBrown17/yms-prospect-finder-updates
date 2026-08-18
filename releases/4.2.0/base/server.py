#!/usr/bin/env python3
"""YMS Prospect Finder OTA verification bridge 4.1.2."""
import os, re, sys, time, shutil
from pathlib import Path
TARGET_VERSION = "4.1.2"
APP_DIR = Path(__file__).resolve().parent
if sys.platform == "darwin":
    DATA_DIR = Path.home() / "Library" / "Application Support" / "YMS Prospect Finder V3"
elif os.name == "nt":
    DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "YMS Prospect Finder V3"
else:
    DATA_DIR = Path.home() / ".yms_prospect_finder_v3"
def fail(message):
    try: (DATA_DIR / "update_restart_error.txt").write_text(str(message), encoding="utf-8")
    except Exception: pass
    raise SystemExit(str(message))
backups = DATA_DIR / "update-backups"
choices=[]
if backups.exists():
    for p in backups.glob("before-" + TARGET_VERSION + "-*"):
        if (p/"server.py").exists() and (p/"index.html").exists():
            try: choices.append((p.stat().st_mtime,p))
            except Exception: pass
if not choices: fail("OTA bridge could not find the safe pre-update backup. No user data was changed.")
backup=max(choices,key=lambda x:x[0])[1]
try:
    source=(backup/"server.py").read_text("utf-8")
    source,count=re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', f'APP_VERSION = "{TARGET_VERSION}"', source, count=1)
    if count!=1: fail("OTA bridge could not update the application version safely.")
    old='                "sha256":plat.get("sha256") or "",\n                "mandatory":bool(manifest.get("mandatory",False)),'
    new='                "sha256":plat.get("sha256") or "",\n                "git_blob_sha":plat.get("git_blob_sha") or "",\n                "mandatory":bool(manifest.get("mandatory",False)),'
    if old not in source: fail("Could not locate updater manifest parser in the safe backup.")
    source=source.replace(old,new,1)
    old='            if result["available"] and (not result["package_url"] or not re.fullmatch(r"[a-fA-F0-9]{64}", result["sha256"] or "")):\n                raise RuntimeError("An update is listed, but its verified package details are incomplete.")'
    new='            sha_ok=bool(re.fullmatch(r"[a-fA-F0-9]{64}", result.get("sha256") or ""))\n            git_ok=bool(re.fullmatch(r"[a-fA-F0-9]{40}", result.get("git_blob_sha") or ""))\n            if result["available"] and (not result["package_url"] or not (sha_ok or git_ok)):\n                raise RuntimeError("An update is listed, but its verified package details are incomplete.")'
    if old not in source: fail("Could not locate updater manifest validation in the safe backup.")
    source=source.replace(old,new,1)
    old='    digest=hashlib.sha256(raw).hexdigest().lower()\n    if digest != str(status["sha256"]).lower():\n        raise RuntimeError("Update verification failed (SHA-256 mismatch). Nothing was changed.")'
    new='    digest=hashlib.sha256(raw).hexdigest().lower()\n    git_digest=hashlib.sha1(("blob "+str(len(raw))+"\\0").encode("ascii")+raw).hexdigest().lower()\n    expected_sha=str(status.get("sha256") or "").lower()\n    expected_git=str(status.get("git_blob_sha") or "").lower()\n    sha_ok=bool(re.fullmatch(r"[a-f0-9]{64}",expected_sha)) and digest==expected_sha\n    git_ok=bool(re.fullmatch(r"[a-f0-9]{40}",expected_git)) and git_digest==expected_git\n    if not (sha_ok or git_ok):\n        raise RuntimeError("Update verification failed. SHA-256 actual="+digest+"; Git blob actual="+git_digest+". Nothing was changed.")'
    if old not in source: fail("Could not locate updater package verification in the safe backup.")
    source=source.replace(old,new,1)
    tmp=APP_DIR/"server.py.ota-new"; tmp.write_text(source,encoding="utf-8"); os.replace(tmp,APP_DIR/"server.py")
    shutil.copy2(backup/"index.html",APP_DIR/"index.html")
    (DATA_DIR/"last_ota_update.txt").write_text(f"{TARGET_VERSION}\n{time.strftime('%Y-%m-%d %H:%M:%S')}\nVerified OTA bridge active\n",encoding="utf-8")
except Exception as exc: fail(exc)
os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])
