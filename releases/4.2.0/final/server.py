#!/usr/bin/env python3
"""YMS Prospect Finder V4.2 Smart Finder OTA patcher.

This is intentionally a small patch package. The updater creates a safe backup
of the currently working app before installing it. This patcher transforms that
backup into V4.2, validates the result, then atomically installs it.
"""
import os, re, sys, time, shutil
from pathlib import Path

TARGET_VERSION = "4.2.0"
APP_DIR = Path(__file__).resolve().parent
if sys.platform == "darwin":
    DATA_DIR = Path.home() / "Library" / "Application Support" / "YMS Prospect Finder V3"
elif os.name == "nt":
    DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "YMS Prospect Finder V3"
else:
    DATA_DIR = Path.home() / ".yms_prospect_finder_v3"

backup = None

def fail(message):
    global backup
    try:
        (DATA_DIR / "update_restart_error.txt").write_text(str(message), encoding="utf-8")
    except Exception:
        pass
    # Restore the pre-update app if the patch failed after files were touched.
    try:
        if backup and (backup / "server.py").exists() and (backup / "index.html").exists():
            shutil.copy2(backup / "server.py", APP_DIR / "server.py")
            shutil.copy2(backup / "index.html", APP_DIR / "index.html")
            os.execv(sys.executable, [sys.executable, str(APP_DIR / "server.py")])
    except Exception:
        pass
    raise SystemExit(str(message))


def extract_raw_assignment(source, name):
    marker = name + "=r'''"
    start = source.find(marker)
    if start < 0:
        marker = name + " = r'''"
        start = source.find(marker)
    if start < 0:
        raise RuntimeError(f"Could not recover {name} from Smart Finder patch source")
    body_start = source.find("'''", start) + 3
    body_end = source.find("'''", body_start)
    if body_end < 0:
        raise RuntimeError(f"Recovered {name} block is incomplete")
    return source[body_start:body_end]


def patch_backend(source, SERVER_INSERT):
    source, count = re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', 'APP_VERSION = "4.2.0"', source, count=1)
    if count != 1:
        raise RuntimeError("Could not locate APP_VERSION in the working application backup")

    source = source.replace(
        '    c.setdefault("hide_noise_by_default", True)\n',
        '    c.setdefault("hide_noise_by_default", True)\n    c.setdefault("smart_finder_query_limit", 100)\n    c.setdefault("smart_finder_pages", 1)\n',
        1,
    )
    source = source.replace(
        '        "hide_noise_by_default":bool(c.get("hide_noise_by_default",True)),\n',
        '        "hide_noise_by_default":bool(c.get("hide_noise_by_default",True)),\n        "smart_finder_query_limit":int(c.get("smart_finder_query_limit",100) or 100),\n        "smart_finder_pages":int(c.get("smart_finder_pages",1) or 1),\n',
        1,
    )

    source = source.replace(
        '    "clothing_store","shoe_store","jewelry_store","book_store","pet_store"\n}',
        '    "clothing_store","shoe_store","jewelry_store","book_store","pet_store",\n    "shopping_mall","gas_station","car_dealer","car_rental","car_wash","parking",\n    "tourist_attraction","museum","library","place_of_worship"\n}',
        1,
    )
    source = source.replace(
        '    ("Wetherspoon", r"\\bwetherspoons?\\b|\\bj\\.?d\\.? wetherspoon\\b"),\n]',
        '    ("Wetherspoon", r"\\bwetherspoons?\\b|\\bj\\.?d\\.? wetherspoon\\b"),\n    ("B&Q", r"\\bb\\s*&\\s*q\\b"), ("IKEA", r"\\bikea\\b"), ("Halfords", r"\\bhalfords\\b"),\n    ("Primark", r"\\bprimark\\b"), ("Poundland", r"\\bpoundland\\b"), ("Home Bargains", r"\\bhome bargains\\b"),\n]',
        1,
    )

    # Return concrete IDs from discovery upserts so Finder can queue only genuinely new/merged prospects.
    source = source.replace(
        '        all_leads=load_json(LEADS_FILE,[]);added=merged=0\n',
        '        all_leads=load_json(LEADS_FILE,[]);added=merged=0;added_ids=[];merged_ids=[]\n',
        1,
    )
    source = source.replace(
        '                merge_into(cand,n);merged+=1\n',
        '                merge_into(cand,n);merged+=1\n                if cand.get("id") and cand.get("id") not in merged_ids:merged_ids.append(cand.get("id"))\n',
        1,
    )
    source = source.replace(
        '                all_leads.append(n);added+=1\n',
        '                all_leads.append(n);added+=1\n                if n.get("id"):added_ids.append(n.get("id"))\n',
        1,
    )
    source = source.replace(
        '        return {"added":added,"merged":merged,"total":len(all_leads)}\n',
        '        return {"added":added,"merged":merged,"total":len(all_leads),"added_ids":added_ids,"merged_ids":merged_ids}\n',
        1,
    )

    marker = 'def _action_complete(l, action):\n'
    if marker not in source:
        raise RuntimeError("Could not locate Smart Pipeline action-complete hook")
    source = source.replace(marker, SERVER_INSERT + '\n\n' + marker, 1)
    source = source.replace('    class SkipProspect(Exception):pass\n', '', 1)

    # Reuse the new relevance-gated one-company pipeline for the existing one-click Smart Pipeline.
    start = '        if action=="pipeline":\n            # One-click YMS workflow: website -> evidence -> AI -> priority/draft -> optional Capsule.\n'
    end = '            return {"status":"done","id":id_,"company":company,"pos":work_pos}\n\n        if action=="ai":\n'
    a = source.find(start)
    b = source.find(end, a)
    if a < 0 or b < 0:
        raise RuntimeError("Could not locate existing Smart Pipeline worker block")
    replacement = '        if action=="pipeline":\n            rr=_process_pipeline_lead(id_,job_id,min(selected_total,already_done+work_pos+1),selected_total)\n            return {"status":rr.get("status","done"),"id":id_,"company":company,"pos":work_pos}\n\n        if action=="ai":\n'
    source = source[:a] + replacement + source[b + len(end):]

    old = '    threading.Thread(target=_run_progress_job,args=(job_id,action,ids),daemon=True).start();return _job_get(job_id)\n'
    new = '    if action=="finder":threading.Thread(target=_run_smart_finder,args=(job_id,),daemon=True).start()\n    else:threading.Thread(target=_run_progress_job,args=(job_id,action,ids),daemon=True).start()\n    return _job_get(job_id)\n'
    if old not in source:
        raise RuntimeError("Could not locate resumable-job launch hook")
    source = source.replace(old, new, 1)

    source = source.replace(
        '            if p=="/api/job/recent":\n                self.sendj(_job_recent() or {});return\n',
        '            if p=="/api/job/recent":\n                self.sendj(_job_recent() or {});return\n            if p=="/api/finder/status":\n                self.sendj(smart_finder_status());return\n',
        1,
    )
    source = source.replace(
        '                if "hide_noise_by_default" in b:c["hide_noise_by_default"]=bool(b.get("hide_noise_by_default"))\n',
        '                if "hide_noise_by_default" in b:c["hide_noise_by_default"]=bool(b.get("hide_noise_by_default"))\n                if "smart_finder_query_limit" in b:c["smart_finder_query_limit"]=max(1,min(int(b.get("smart_finder_query_limit") or 100),1000))\n                if "smart_finder_pages" in b:c["smart_finder_pages"]=max(1,min(int(b.get("smart_finder_pages") or 1),3))\n',
        1,
    )
    source = source.replace(
        '            if p=="/api/job/start":\n',
        '            if p=="/api/finder/start":\n                self.sendj(start_smart_finder(b.get("query_limit",cfg().get("smart_finder_query_limit",100)),b.get("pages",cfg().get("smart_finder_pages",1))));return\n            if p=="/api/finder/stop":\n                self.sendj(stop_smart_finder());return\n            if p=="/api/job/start":\n',
        1,
    )
    return source


def patch_frontend(html, CSS_INSERT, FINDER_DASH, FINDER_DISCOVER):
    platform = "Mac" if sys.platform == "darwin" else ("Windows" if os.name == "nt" else "Desktop")
    html = re.sub(r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>', f'<title>YMS Prospect Finder V4.2.0 {platform} — YMS-Tools</title>', html, count=1)
    html = re.sub(r'<b id="versionLabel">Prospect Finder V[^<]+</b>', f'<b id="versionLabel">Prospect Finder V4.2.0 {platform}</b>', html, count=1)
    if '\n</style></head>' not in html:
        raise RuntimeError("Could not locate application stylesheet end")
    html = html.replace('\n</style></head>', '\n' + CSS_INSERT + '\n</style></head>', 1)

    hero_end = '</div></div></div>\n<div class="v4Queue">'
    if hero_end not in html:
        raise RuntimeError("Could not locate Dashboard hero insertion point")
    html = html.replace(hero_end, '</div></div></div>\n' + FINDER_DASH + '\n<div class="v4Queue">', 1)
    discover = '<section id="discover" class="view">\n<div class="grid">'
    if discover not in html:
        raise RuntimeError("Could not locate Discover grid")
    html = html.replace(discover, discover + '\n' + FINDER_DISCOVER, 1)

    old_notice = '<div class="notice good"><b>Always automatic:</b> live list refresh, Mac ↔ Windows sync polling, duplicate prevention, completed-scan skipping, per-company safe checkpoints, personalised email drafting and resumable background jobs.</div>'
    if old_notice in html:
        html = html.replace(old_notice, '<div class="notice good"><b>Always automatic:</b> live list refresh, Mac ↔ Windows sync polling, duplicate prevention, completed-scan skipping, per-company safe checkpoints, personalised email drafting, resumable jobs and V4.2 website relevance filtering before AI.</div>', 1)

    target = '<div class="toggleRow"><div><b>Hide obvious noise by default</b><span>Keeps supermarkets, restaurants and other rejected consumer results out of your normal sales queue.</span></div><select id="hideNoiseDefault" class="switchSelect"><option value="true">ON</option><option value="false">OFF</option></select></div>'
    if target in html:
        repl = target + '<div class="toggleRow"><div><b>Smart Finder default run</b><span>Used by the one-click Dashboard button. You can override these from Discover.</span></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;min-width:210px"><select id="finderQueriesSetting" class="switchSelect"><option>25</option><option>50</option><option>100</option><option>250</option><option>500</option></select><select id="finderPagesSetting" class="switchSelect"><option>1</option><option>2</option><option>3</option></select></div></div>'
        html = html.replace(target, repl, 1)

    html = html.replace('id="updateSettingsBadge">V4.1<', 'id="updateSettingsBadge">V4.2<')
    html = html.replace('pointing at this V4.1.0 folder', 'pointing at this V4.2.0 folder')

    JS = r'''
let finderLastStatus=null,finderPollToken=0;
function finderPut(id,v){if($(id))$(id).textContent=String(v??0)}
function paintFinderStatus(j){j=j||{};finderLastStatus=j;let running=j.status==="running"||j.status==="queued",paused=j.status==="paused",q=Number(j.queries_done||0),limit=Number(j.query_limit||0);finderPut("fdQueries",limit?`${q}/${limit}`:q);finderPut("fcQueries",limit?`${q}/${limit}`:q);finderPut("fdHits",Number(j.google_hits||0).toLocaleString());finderPut("fcHits",Number(j.google_hits||0).toLocaleString());finderPut("fdNew",Number(j.new_candidates||0).toLocaleString());finderPut("fcNew",Number(j.new_candidates||0).toLocaleString());finderPut("fdFiltered",Number(j.filtered||0).toLocaleString());finderPut("fcFiltered",Number(j.filtered||0).toLocaleString());finderPut("fcNoise",Number(j.noise_blocked||0).toLocaleString());finderPut("fdAI",Number(j.qualified||0).toLocaleString());finderPut("fcAI",Number(j.qualified||0).toLocaleString());finderPut("fdWaiting",Number(j.waiting||0).toLocaleString());["finderDashStart","finderStartBtn"].forEach(id=>{if($(id))$(id).disabled=running||paused});["finderDashStop","finderStopBtn"].forEach(id=>{if($(id))$(id).disabled=!running});let text=j.detail||"Smart Finder is idle.";finderPut("finderDashText",text);if($("finderControlText")){$("finderControlText").innerHTML=`<b>${esc(String(j.status||"idle").toUpperCase())}</b> • ${esc(text)}${running?` • ${Number(j.active_workers||0)} active pipeline workers • ${Number(j.waiting||0)} waiting`:""}`;$("finderControlText").className=paused?"notice warn":running?"notice good":"notice"}if($("finderDashDot"))$("finderDashDot").className="finderDot"+(running?" live":paused?" paused":"")}
async function refreshFinderStatus(){try{paintFinderStatus(await api("/api/finder/status"))}catch(e){}}
async function pollFinderJob(id){let token=++finderPollToken;for(;;){if(token!==finderPollToken)return;try{let j=await api(`/api/job?id=${encodeURIComponent(id)}`);paintFinderStatus(j);if(typeof paintJob==="function")paintJob(j);if(["complete","failed","paused"].includes(j.status)){await refreshLeads();if(j.status==="complete")toast("Smart Finder finished. New scores and email priorities are already in Prospects.","good",6000);return}}catch(e){return}await new Promise(r=>setTimeout(r,1200))}}
async function startSmartFinder(fromDashboard=false){if(conf.free_mode){toast("Smart Finder needs Full Mode because it automatically AI-qualifies relevant companies after the relevance filters.","warn",6500);showById("settings");return}let limit=Number($("finderQueries")?.value||conf.smart_finder_query_limit||100),pages=Number($("finderPages")?.value||conf.smart_finder_pages||1);if(fromDashboard){limit=Number(conf.smart_finder_query_limit||100);pages=Number(conf.smart_finder_pages||1)}if(!confirm(`Start Smart Finder?\n\n${limit} Google searches across all YMS sectors. Finding, website checking and AI qualification will run together. Obvious consumer noise is rejected before OpenAI.`))return;try{let j=await api("/api/finder/start",{query_limit:limit,pages});paintFinderStatus(j);if(typeof showProgress==="function")showProgress("Smart Finder • all YMS sectors",j.created_at||0);if(typeof paintJob==="function")paintJob(j);pollFinderJob(j.id)}catch(e){toast(e.message,"bad",7500)}}
async function stopSmartFinder(){try{let j=await api("/api/finder/stop",{});paintFinderStatus(j);toast(j.message||"Stop requested.","good",5000)}catch(e){toast(e.message,"bad",6000)}}
'''
    marker = 'function show(id,b){'
    if marker not in html:
        raise RuntimeError("Could not locate JavaScript helper insertion point")
    html = html.replace(marker, JS + '\n' + marker, 1)

    boot_old = 'refreshUpdateStatus(false);setInterval(refreshSyncStatus,5000);setInterval(refreshLeadsIfChanged,2000)'
    if boot_old in html:
        html = html.replace(boot_old, 'refreshUpdateStatus(false);refreshFinderStatus();setInterval(refreshSyncStatus,5000);setInterval(refreshLeadsIfChanged,2000);setInterval(refreshFinderStatus,2000)', 1)

    # Live Finder metrics in the existing activity panel.
    old_count = '$("progressCount").textContent=parts.join(" • ");'
    if old_count in html:
        new_count = 'if(j.action==="finder")parts=[`${j.queries_done||0}/${j.query_limit||0} searches`,`${j.google_hits||0} Google hits`,`${j.noise_blocked||0} obvious noise`,`${j.filtered||0} filtered before AI`,`${j.qualified||0} qualified`,`${j.waiting||0} waiting`];$("progressCount").textContent=parts.join(" • ");'
        html = html.replace(old_count, new_count, 1)

    # Make Finder resumable from the same activity panel as other background jobs.
    resume_old = 'async function resumeProgressJob(){'
    if resume_old in html:
        html = html.replace(resume_old, 'async function resumeProgressJob(){if(activeProgressLatestJob?.action==="finder"){try{let j=await api("/api/job/resume",{id:activeProgressLatestJob.id});paintFinderStatus(j);paintJob(j);pollFinderJob(j.id)}catch(e){toast(e.message,"bad",6500)}return}', 1)

    # Persist/load default run size when the existing config form supports the new fields.
    save_anchor = 'hide_noise_by_default:$("hideNoiseDefault").value==="true"'
    if save_anchor in html:
        html = html.replace(save_anchor, save_anchor + ',smart_finder_query_limit:Number($("finderQueriesSetting")?.value||100),smart_finder_pages:Number($("finderPagesSetting")?.value||1)', 1)
    load_anchor = 'if($("hideNoiseDefault"))$("hideNoiseDefault").value=String(c.hide_noise_by_default!==false);'
    if load_anchor in html:
        html = html.replace(load_anchor, load_anchor + 'if($("finderQueriesSetting"))$("finderQueriesSetting").value=String(c.smart_finder_query_limit||100);if($("finderPagesSetting"))$("finderPagesSetting").value=String(c.smart_finder_pages||1);', 1)

    return html


try:
    smart_patch_path = APP_DIR / "smart_patch.txt"
    if not smart_patch_path.exists():
        fail("Smart Finder patch data is missing from the update package.")
    smart_source = smart_patch_path.read_text("utf-8", errors="replace")
    SERVER_INSERT = extract_raw_assignment(smart_source, "SERVER_INSERT")
    CSS_INSERT = extract_raw_assignment(smart_source, "CSS_INSERT")
    FINDER_DASH = extract_raw_assignment(smart_source, "FINDER_DASH")
    FINDER_DISCOVER = extract_raw_assignment(smart_source, "FINDER_DISCOVER")

    backups = DATA_DIR / "update-backups"
    choices = []
    if backups.exists():
        for p in backups.glob("before-" + TARGET_VERSION + "-*"):
            if (p / "server.py").exists() and (p / "index.html").exists():
                try:
                    choices.append((p.stat().st_mtime, p))
                except Exception:
                    pass
    if not choices:
        fail("V4.2 could not find the safe pre-update backup. Nothing was changed.")
    backup = max(choices, key=lambda x: x[0])[1]

    backend = (backup / "server.py").read_text("utf-8")
    frontend = (backup / "index.html").read_text("utf-8")
    backend = patch_backend(backend, SERVER_INSERT)
    frontend = patch_frontend(frontend, CSS_INSERT, FINDER_DASH, FINDER_DISCOVER)

    # Compile the exact generated backend before replacing anything.
    compile(backend, "server.py", "exec")
    required_backend = ["APP_VERSION = \"4.2.0\"", "def start_smart_finder", "/api/finder/start", "def website_relevance_gate"]
    required_frontend = ["SMART FINDER • V4.2", "startSmartFinder", "finderControlCard"]
    missing = [x for x in required_backend if x not in backend] + [x for x in required_frontend if x not in frontend]
    if missing:
        raise RuntimeError("Generated V4.2 failed validation: " + ", ".join(missing))

    server_tmp = APP_DIR / "server.py.ota-new"
    index_tmp = APP_DIR / "index.html.ota-new"
    server_tmp.write_text(backend, encoding="utf-8")
    index_tmp.write_text(frontend, encoding="utf-8")
    os.replace(server_tmp, APP_DIR / "server.py")
    os.replace(index_tmp, APP_DIR / "index.html")
    try:
        smart_patch_path.unlink()
    except Exception:
        pass
    (DATA_DIR / "last_ota_update.txt").write_text(
        f"4.2.0\n{time.strftime('%Y-%m-%d %H:%M:%S')}\nSmart Finder installed and validated\n",
        encoding="utf-8",
    )
except Exception as exc:
    fail(exc)

os.execv(sys.executable, [sys.executable, str(APP_DIR / "server.py")])
