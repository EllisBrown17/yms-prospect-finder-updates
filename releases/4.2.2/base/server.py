#!/usr/bin/env python3
"""YMS Prospect Finder V4.2.1 — individual prospect workflow fix.

This OTA patch keeps V4.2 Smart Finder intact and fixes the opened-prospect
Website evidence / AI qualify buttons so they automatically complete prerequisite
steps, retry previously skipped records, refresh the drawer, and surface a clear
result instead of silently doing nothing.
"""
import os, re, sys, time, shutil, hashlib, zipfile, io
from urllib import request
from pathlib import Path

TARGET_VERSION = "4.2.1"
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
    msg = str(message)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "update_restart_error.txt").write_text(msg, encoding="utf-8")
    except Exception:
        pass
    try:
        if backup and (backup / "server.py").exists() and (backup / "index.html").exists():
            shutil.copy2(backup / "server.py", APP_DIR / "server.py")
            shutil.copy2(backup / "index.html", APP_DIR / "index.html")
            os.execv(sys.executable, [sys.executable, str(APP_DIR / "server.py")])
    except Exception:
        pass
    raise SystemExit(msg)


def req(text, old, new, label, count=1):
    if old not in text:
        raise RuntimeError(f"V4.2.1 could not locate {label}; the working app was left unchanged.")
    return text.replace(old, new, count)


WEB_ONE_BLOCK = r'''        if action=="web_one":
            # Manual retry: unlike bulk pre-scan, explicitly clicking Website evidence
            # retries old skip markers and can resolve a missing Google Place first.
            if hard_noise_reason(l) or l.get("discovery_excluded"):
                raise SkipProspect(l.get("discovery_exclusion_reason") or "Obvious non-industrial / irrelevant result")
            def update_cb_one(page_index,page_total,message,current_url,pages_found):
                _job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company,company_index=min(selected_total,already_done+work_pos+1))
            if not l.get("website") and not l.get("place_id"):
                _job_set(job_id,detail=f"Finding company on Google • {company}",company=company,current_url="")
                r=resolve_google_for_ch(l)
                if r.get("matched"):
                    update_lead(id_,lambda x:merge_into(x,r["lead"]))
                    l=get_lead(id_) or l
            if not l.get("website") and l.get("place_id"):
                key=cfg().get("google_places_key")
                if not key:raise SkipProspect("Google Places is not configured")
                _job_set(job_id,detail=f"Finding company website • {company}",company=company,current_url="")
                p2=google_details(l["place_id"],key,"enterprise")
                def apply_google_one(x):merge_into(x,gp_to_lead(p2,x.get("sector",""),"Google enterprise enrichment"));return dict(x)
                update_lead(id_,apply_google_one);l=get_lead(id_) or l
            if not l.get("website"):
                reason="No company website found after Google lookup"
                update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True))
                raise SkipProspect(reason)
            _job_set(job_id,detail=f"Reading website evidence • {company}",company=company,current_url=l.get("website",""))
            def enrich_one_manual(x):
                ev=web_enrich(x,update_cb_one);x["web_evidence"]=ev;x["emails"]=merge_lists(x.get("emails",[]),ev.get("emails",[]))
                if ev.get("contact_page"):x["contact_page"]=ev["contact_page"]
                if ev.get("linkedin_url"):x["linkedin_url"]=ev["linkedin_url"]
                x.pop("web_skip_reason",None);return ev
            ev=update_lead(id_,enrich_one_manual) or {}
            if not ev.get("text"):
                reason="Website found, but no usable business pages could be read"
                update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True))
                raise SkipProspect(reason)
            return {"status":"done","id":id_,"company":company,"pos":work_pos}

'''

AI_ONE_BLOCK = r'''        if action=="ai_one":
            # Manual AI is a one-company Smart Pipeline: resolve website -> crawl ->
            # relevance gate -> OpenAI -> score/priority/email draft. It retries stale skips.
            if hard_noise_reason(l) or l.get("discovery_excluded"):
                raise SkipProspect(l.get("discovery_exclusion_reason") or "Obvious non-industrial / irrelevant result")
            if not l.get("website") and not l.get("place_id"):
                _job_set(job_id,detail=f"Finding company on Google • {company}",company=company,current_url="")
                r=resolve_google_for_ch(l)
                if r.get("matched"):
                    update_lead(id_,lambda x:merge_into(x,r["lead"]))
                    l=get_lead(id_) or l
            if not l.get("website") and l.get("place_id"):
                key=cfg().get("google_places_key")
                if not key:raise SkipProspect("Google Places is not configured")
                _job_set(job_id,detail=f"Finding company website • {company}",company=company,current_url="")
                p2=google_details(l["place_id"],key,"enterprise")
                def apply_google_ai_one(x):merge_into(x,gp_to_lead(p2,x.get("sector",""),"Google enterprise enrichment"));return dict(x)
                update_lead(id_,apply_google_ai_one);l=get_lead(id_) or l
            if not l.get("website"):
                reason="No company website found after Google lookup — AI not run"
                update_lead(id_,lambda x:(x.update({"web_skip_reason":"No company website found after Google lookup","ai_skip_reason":reason}) or True))
                raise SkipProspect(reason)
            ev=l.get("web_evidence") or {}
            if not ev.get("text"):
                def ai_one_progress(page_index,page_total,message,current_url,pages_found):
                    _job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company,company_index=min(selected_total,already_done+work_pos+1))
                _job_set(job_id,detail=f"Reading website evidence • {company}",company=company,current_url=l.get("website",""))
                def ai_one_enrich(x):
                    ev2=web_enrich(x,ai_one_progress);x["web_evidence"]=ev2;x["emails"]=merge_lists(x.get("emails",[]),ev2.get("emails",[]))
                    if ev2.get("contact_page"):x["contact_page"]=ev2["contact_page"]
                    if ev2.get("linkedin_url"):x["linkedin_url"]=ev2["linkedin_url"]
                    x.pop("web_skip_reason",None);return ev2
                ev=update_lead(id_,ai_one_enrich) or {}
                if not ev.get("text"):
                    reason="Website found, but no usable business evidence could be read — AI not run"
                    update_lead(id_,lambda x:(x.update({"web_skip_reason":"No usable website evidence","ai_skip_reason":reason}) or True))
                    raise SkipProspect(reason)
            # V4.2 has the deterministic website relevance gate. Keep compatibility
            # with older bases so this fix can still roll back safely if necessary.
            gate_fn=globals().get("apply_website_relevance_gate")
            if callable(gate_fn):
                gate=gate_fn(id_)
                if not gate.get("pass"):
                    reason="Filtered before AI — "+str(gate.get("reason") or "not relevant")
                    update_lead(id_,lambda x:(x.update({"ai_skip_reason":reason}) or True))
                    raise SkipProspect(reason)
            l=get_lead(id_) or l
            _job_set(job_id,detail=f"AI qualifying • {company}",company=company,current_url=l.get("website",""),company_index=min(selected_total,already_done+work_pos+1))
            result=_ai_with_retry(job_id,l,0,0,company)
            _job_set(job_id,detail=f"Saving YMS score, priority + email draft • {company}",company=company,current_url="")
            def save_ai_one(x):
                x["ai"]=result;x.pop("ai_skip_reason",None);x.pop("web_skip_reason",None);return result
            update_lead(id_,save_ai_one)
            current=get_lead(id_) or {}
            if cfg().get("auto_capsule_high_priority",False) and cfg().get("capsule_token") and current.get("outreach_priority_code") in ("P1","P2") and not (current.get("capsule") or {}).get("capsule_id"):
                _job_set(job_id,detail=f"Sending high-priority prospect to Capsule • {company}",company=company,current_url="")
                update_lead(id_,lambda x:(x.update({"capsule":capsule_sync(x)}) or x["capsule"]))
            return {"status":"done","id":id_,"company":company,"pos":work_pos}

'''



V42_BOOTSTRAP_URL = "https://raw.githubusercontent.com/EllisBrown17/yms-prospect-finder-updates/main/releases/4.2.0/YMS_Prospect_Finder_V4_2_0_FINAL.zip"
V42_BOOTSTRAP_SHA256 = "b13c9b9bffc226206cb849df5d763b16630325b1f91381eeabd33f1c11186773"

def bootstrap_v42_if_needed(server_source, html_source):
    """Allow a device still on V4.1.x to jump safely to V4.2.1 in one OTA step."""
    if 'def start_smart_finder(' in server_source and 'id="finderDashCard"' in html_source:
        return server_source, html_source
    req = request.Request(V42_BOOTSTRAP_URL, headers={"User-Agent":"YMS-Prospect-Finder-V4.2.1-bootstrap","Accept":"application/zip"})
    with request.urlopen(req, timeout=60) as r:
        raw = r.read(25_000_000)
    if hashlib.sha256(raw).hexdigest().lower() != V42_BOOTSTRAP_SHA256:
        raise RuntimeError("Could not verify the V4.2 Smart Finder prerequisite package")
    with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
        bad = z.testzip()
        if bad: raise RuntimeError("V4.2 prerequisite archive is damaged: "+bad)
        v42_patcher = z.read("server.py").decode("utf-8")
        smart_payload = z.read("smart_patch.txt").decode("utf-8")
    cut = v42_patcher.find("# Locate the exact safe app backup")
    if cut < 0: cut = v42_patcher.find("# Locate the exact safe app backup created")
    if cut < 0: raise RuntimeError("V4.2 prerequisite patcher structure is not recognised")
    ns={"__file__":str(APP_DIR/"_v42_bootstrap.py")}
    exec(v42_patcher[:cut],ns)
    extract=ns.get("extract_raw_assignment") or ns.get("extract_block")
    if not callable(extract): raise RuntimeError("V4.2 prerequisite payload reader is unavailable")
    server_insert=extract(smart_payload,"SERVER_INSERT")
    css=extract(smart_payload,"CSS_INSERT")
    dash=extract(smart_payload,"FINDER_DASH")
    discover=extract(smart_payload,"FINDER_DISCOVER")
    v42_server=ns["patch_backend"](server_source,server_insert)
    v42_html=ns["patch_frontend"](html_source,css,dash,discover)
    compile(v42_server,"v4.2-bootstrap-server.py","exec")
    if 'def start_smart_finder(' not in v42_server or 'id="finderDashCard"' not in v42_html:
        raise RuntimeError("V4.2 Smart Finder prerequisite validation failed")
    return v42_server,v42_html


def patch_backend(source):
    source, n = re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', f'APP_VERSION = "{TARGET_VERSION}"', source, count=1)
    if n != 1:
        raise RuntimeError("Could not update APP_VERSION")

    # Make manual actions proper AI/network actions for retry / quota classification.
    source = source.replace('if action in ("ai","pipeline"):', 'if action in ("ai","ai_one","pipeline"):', 1)
    # Free Mode continues to allow one manual AI action, but not multi-company calls.
    source = source.replace('if action in ("ai","pipeline") and cfg().get("free_mode",True) and len(raw)>1:', 'if action in ("ai","ai_one","pipeline") and cfg().get("free_mode",True) and len(raw)>1:', 1)

    # Insert explicit retryable one-company actions before the legacy bulk actions.
    web_marker = '        if action=="web":\n            def update_cb(page_index,page_total,message,current_url,pages_found):\n'
    source = req(source, web_marker, WEB_ONE_BLOCK + web_marker, "individual website worker insertion")
    ai_marker = '        if action=="ai":\n            ev=l.get("web_evidence") or {}\n'
    source = req(source, ai_marker, AI_ONE_BLOCK + ai_marker, "individual AI worker insertion")

    # Manual skip/failure bookkeeping should be treated like the equivalent legacy action.
    source = source.replace('if action=="web":update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True))', 'if action in ("web","web_one"):update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True))', 1)
    source = source.replace('elif action in ("ai","pipeline"):update_lead(id_,lambda x:(x.update({"ai_skip_reason":reason}) or True))', 'elif action in ("ai","ai_one","pipeline"):update_lead(id_,lambda x:(x.update({"ai_skip_reason":reason}) or True))', 1)
    source = source.replace('if action in ("ai","pipeline") and kind=="ai_response":', 'if action in ("ai","ai_one","pipeline") and kind=="ai_response":', 1)
    return source


ONE_JS = r'''function prospectWorkNotice(l){
 let msg="",kind="warn";
 if(!l.ai&&l.ai_skip_reason)msg=l.ai_skip_reason;
 else if(!(l.web_evidence||{}).text&&l.web_skip_reason)msg=l.web_skip_reason;
 if(!msg)return "";
 return `<div class="notice ${kind}" style="margin-top:9px"><b>Last attempt:</b> ${esc(msg)}</div>`;
}
async function runOneProspectStep(action,id,title){
 try{
  let j=await runProgressJob(action,[id],title);
  await loadLeads();openD(id);
  let l=leads.find(x=>x.id===id),reason=action==="web_one"?(l?.web_skip_reason||""):(l?.ai_skip_reason||l?.web_skip_reason||"");
  if(Number(j.skipped)||reason){toast(reason||"This step could not be completed. The reason is shown in the prospect drawer.","warn",7500)}
  else{toast(action==="web_one"?"Website evidence updated.":"AI qualification complete — score, priority and email draft updated.","good",5200)}
  return j;
 }catch(e){
  await loadLeads();openD(id);alert(e.message);
 }
}
'''


def patch_frontend(html):
    platform = "Mac" if sys.platform == "darwin" else ("Windows" if os.name == "nt" else "Desktop")
    html = re.sub(r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>', f'<title>YMS Prospect Finder V{TARGET_VERSION} {platform} — YMS-Tools</title>', html, count=1)
    html = re.sub(r'<b id="versionLabel">Prospect Finder V[^<]+</b>', f'<b id="versionLabel">Prospect Finder V{TARGET_VERSION} {platform}</b>', html, count=1)

    old_strip = '<div class="v4ActionStrip"><div class="copy"><b>Work this prospect</b><span>Only missing steps are actually run.</span></div><div class="actions">${!l.place_id?`<button class="btn sm" onclick="act(\'${id}\',\'/api/resolve-google\',\'Finding\',this)">Find on Google</button>`:\'\'}<button class="btn sm" ${l.discovery_excluded?\'disabled\':\'\'} onclick="runProgressJob(\'web\',[\'${id}\'],\'Website evidence\')">Website evidence</button><button class="btn sm primary" ${l.discovery_excluded?\'disabled\':\'\'} onclick="aiQualifyOne(\'${id}\',this)">AI qualify</button><button class="btn sm green" onclick="capsule(\'${id}\',this)">${l.capsule?.capsule_id?\'Update Capsule\':\'Send to Capsule\'}</button></div></div>'
    # Use simpler exact fragments because template escaping differs when represented in Python.
    html = req(html,
        '<div class="v4ActionStrip"><div class="copy"><b>Work this prospect</b><span>Only missing steps are actually run.</span></div>',
        '<div class="v4ActionStrip"><div class="copy"><b>Work this prospect</b><span>Missing website/evidence is found automatically. Results refresh here when finished.</span></div>',
        "prospect action-strip copy")
    html = req(html,
        'onclick="runProgressJob(\'web\',[\'${id}\'],\'Website evidence\')">Website evidence</button>',
        'onclick="runOneProspectStep(\'web_one\',\'${id}\',\'Website evidence\')">Website evidence</button>',
        "individual Website evidence button")

    old_ai = 'async function aiQualifyOne(id,btn=null){let lead=leads.find(x=>x.id===id);if(lead?.discovery_excluded){alert("This result was auto-excluded as obvious consumer/non-industrial noise, so AI will not spend money on it.");return}if(!conf.openai_key_set){alert("OpenAI is not configured yet. Add an API key in Settings first.");return}if(!confirm("Run OpenAI qualification for this ONE company? Free Mode allows this manual single-company action only."))return;if(btn){btn.disabled=true;btn.dataset.old=btn.textContent;btn.textContent="Analysing…"}try{await runProgressJob("ai",[id],"AI qualification");openD(id)}catch(e){alert(e.message)}finally{if(btn){btn.disabled=false;btn.textContent=btn.dataset.old||"AI Qualify — this company only"}}}'
    new_ai = ONE_JS + '\nasync function aiQualifyOne(id,btn=null){let lead=leads.find(x=>x.id===id);if(lead?.discovery_excluded){alert("This result was auto-excluded as obvious consumer/non-industrial noise, so AI will not spend money on it.");return}if(!conf.openai_key_set){alert("OpenAI is not configured yet. Add an API key in Settings first.");return}if(!confirm("Qualify this company now?\\n\\nProspect Finder will automatically find its website, read useful evidence, check relevance, then run AI and create the score, priority and personalised email draft."))return;if(btn){btn.disabled=true;btn.dataset.old=btn.textContent;btn.textContent="Working…"}try{await runOneProspectStep("ai_one",id,"One-click prospect qualification")}finally{if(btn){btn.disabled=false;btn.textContent=btn.dataset.old||"AI qualify"}}}'
    html = req(html, old_ai, new_ai, "individual AI function")

    # Surface old/new skip reasons in the drawer so a failed attempt never looks like a dead button.
    drawer_marker = '</div></div>\n<div class="drawerGrid">'
    html = req(html, drawer_marker, '</div></div>\n${prospectWorkNotice(l)}\n<div class="drawerGrid">', "drawer result notice", 1)
    return html


# The updater always creates this backup immediately before replacing the files.
backups = DATA_DIR / "update-backups"
choices = []
if backups.exists():
    for p in backups.glob("before-" + TARGET_VERSION + "-*"):
        if (p / "server.py").exists() and (p / "index.html").exists():
            try: choices.append((p.stat().st_mtime, p))
            except Exception: pass
if not choices:
    fail("V4.2.1 could not find the safe pre-update backup. Nothing in your prospect database was changed.")
backup = max(choices, key=lambda x: x[0])[1]

try:
    old_server = (backup / "server.py").read_text("utf-8")
    old_html = (backup / "index.html").read_text("utf-8")
    old_server, old_html = bootstrap_v42_if_needed(old_server, old_html)
    new_server = patch_backend(old_server)
    new_html = patch_frontend(old_html)
    compile(new_server, "server.py", "exec")
    if f'APP_VERSION = "{TARGET_VERSION}"' not in new_server or 'action=="ai_one"' not in new_server or 'action=="web_one"' not in new_server:
        raise RuntimeError("V4.2.1 backend validation failed")
    if 'runOneProspectStep' not in new_html or "'web_one'" not in new_html or '"ai_one"' not in new_html:
        raise RuntimeError("V4.2.1 interface validation failed")
    tmp_server = APP_DIR / "server.py.ota-new"
    tmp_html = APP_DIR / "index.html.ota-new"
    tmp_server.write_text(new_server, encoding="utf-8")
    tmp_html.write_text(new_html, encoding="utf-8")
    os.replace(tmp_server, APP_DIR / "server.py")
    os.replace(tmp_html, APP_DIR / "index.html")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "last_ota_update.txt").write_text(
        f"{TARGET_VERSION}\n{time.strftime('%Y-%m-%d %H:%M:%S')}\nIndividual Website evidence + AI qualification workflow fixed\n",
        encoding="utf-8",
    )
except Exception as exc:
    fail(exc)

os.execv(sys.executable, [sys.executable, str(APP_DIR / "server.py")])
