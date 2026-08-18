#!/usr/bin/env python3
from pathlib import Path
import os,re,sys,time,shutil
TARGET_VERSION="4.2.0"
APP_DIR=Path(__file__).resolve().parent
if sys.platform=="darwin": DATA_DIR=Path.home()/"Library"/"Application Support"/"YMS Prospect Finder V3"
elif os.name=="nt": DATA_DIR=Path(os.getenv("APPDATA",Path.home()))/"YMS Prospect Finder V3"
else: DATA_DIR=Path.home()/".yms_prospect_finder_v3"

def ota_fail(msg):
    try:(DATA_DIR/"update_restart_error.txt").write_text(str(msg),encoding="utf-8")
    except Exception:pass
    raise SystemExit(str(msg))

SERVER_INSERT = r'''

# ---------------------------------------------------------------------------
# V4.2 Smart Finder — all-sector discovery + concurrent evidence/AI pipeline
# ---------------------------------------------------------------------------
INDUSTRIAL_GENERAL_TERMS = (
    "manufacturer","manufacturing","fabrication","fabricator","steelwork","sheet metal","metalwork",
    "welding","machining","engineering","engineers","workshop","industrial","switchgear","switchboard",
    "control panel","panel builder","electrical enclosure","enclosures","cabinet manufacture","busbar",
    "lifting equipment","rigging","material handling","machine tools","tool hire","ship repair","shipbuilding",
    "marine engineering","offshore engineering","pipe fabrication","pipework","process engineering",
    "server rack","network cabinet","technical furniture","assembly systems","plant fabrication"
)
NON_TARGET_WEB_TERMS = (
    "online grocery","groceries","supermarket","fresh food","food delivery","restaurant menu","book a table",
    "hotel rooms","book a room","pharmacy services","prescriptions","beauty treatments","hair salon",
    "school admissions","student enrolment","estate agency","property lettings","fashion clothing","holiday booking"
)
INDUSTRIAL_NAME_HINTS = re.compile(
    r"\b(engineer(?:ing|s)?|fabricat(?:ion|ors?)|steel(?:work)?|metal(?:work)?|switchgear|switchboard|controls?|"
    r"panel(?:s| builder)?|automation|enclosures?|cabinets?|weld(?:ing|ers?)|machin(?:ing|ery)|industrial|lifting|"
    r"rigging|marine|offshore|pipe(?:work)?|process|tool(?:s| hire)?|rack(?:s)?|manufactur(?:e|er|ing))\b", re.I
)

class SkipProspect(Exception):
    pass


def website_relevance_gate(l):
    """Cheap evidence gate before OpenAI. Conservative: reject only when the site does not show industrial relevance."""
    if not isinstance(l, dict):
        return {"pass": False, "score": 0, "reason": "Invalid prospect record", "sector_hits": [], "industrial_hits": [], "negative_hits": []}
    if l.get("relevance_override") == "include":
        return {"pass": True, "score": 100, "reason": "Manually included", "sector_hits": [], "industrial_hits": [], "negative_hits": []}
    hard=hard_noise_reason(l)
    if hard:
        return {"pass": False, "score": 0, "reason": hard, "sector_hits": [], "industrial_hits": [], "negative_hits": []}
    ev=l.get("web_evidence") or {}
    text=(ev.get("text") or "").lower()
    name=(l.get("company") or "").lower()
    if len(text.strip()) < 180:
        return {"pass": False, "score": 5, "reason": "Website did not provide enough useful business evidence", "sector_hits": [], "industrial_hits": [], "negative_hits": []}
    sector=l.get("sector") or ""
    sector_signals=[str(x).lower() for x in (PRODUCT_RULES.get(sector,{}).get("signals") or []) if str(x).strip()]
    sector_hits=[x for x in sector_signals if x in text]
    industrial_hits=[x for x in INDUSTRIAL_GENERAL_TERMS if x in text]
    negative_hits=[x for x in NON_TARGET_WEB_TERMS if x in text]
    name_industrial=bool(INDUSTRIAL_NAME_HINTS.search(name))
    # Unique terms only; repeated marketing copy should not inflate the score.
    score=min(100, (36 if sector_hits else 0) + min(42,len(industrial_hits)*11) + (14 if name_industrial else 0) - min(45,len(negative_hits)*18))
    relevant=bool(sector_hits) or len(industrial_hits)>=2 or (name_industrial and len(industrial_hits)>=1)
    if len(negative_hits)>=2 and not sector_hits and len(industrial_hits)<2:
        relevant=False
    if relevant:
        reason=(f"Relevant website evidence: {', '.join((sector_hits+industrial_hits)[:4])}" if (sector_hits or industrial_hits) else "Industrial relevance confirmed")
    else:
        reason="Website does not show enough relevant manufacturing, fabrication or industrial engineering activity"
        if negative_hits: reason += f"; non-target signals: {', '.join(negative_hits[:3])}"
    return {"pass": bool(relevant), "score": int(max(0,score)), "reason": reason, "sector_hits": sector_hits[:8], "industrial_hits": industrial_hits[:12], "negative_hits": negative_hits[:8], "checked_at": nowiso()}


def apply_website_relevance_gate(id_):
    l=get_lead(id_)
    gate=website_relevance_gate(l or {})
    def save_gate(x):
        x["discovery_quality"]=gate
        if gate.get("pass"):
            if x.get("discovery_exclusion_source")=="auto-v4.2":
                x["discovery_excluded"]=False;x["discovery_exclusion_reason"]="";x["discovery_exclusion_source"]=""
        elif x.get("relevance_override")!="include":
            x["discovery_excluded"]=True
            x["discovery_exclusion_reason"]=gate.get("reason") or "Website relevance gate failed"
            x["discovery_exclusion_source"]="auto-v4.2"
        return gate
    update_lead(id_,save_gate)
    return gate


def smart_finder_matrix():
    """Round-robin all YMS sectors so broad runs cover every market instead of exhausting one category first."""
    sectors=sorted(PRODUCT_RULES.keys(), key=lambda s:int(PRODUCT_RULES[s].get("priority",0)), reverse=True)
    max_terms=max((len(PRODUCT_RULES[s].get("google_terms") or []) for s in sectors), default=0)
    jobs=[]
    for area in UK_AREAS:
        for term_index in range(max_terms):
            for sector in sectors:
                terms=PRODUCT_RULES[sector].get("google_terms") or []
                if term_index < len(terms):
                    jobs.append((sector,area,terms[term_index]))
    return jobs


def _finder_job_latest():
    with JOB_LOCK:
        rows=[dict(j) for j in JOBS.values() if j.get("action")=="finder"]
    if not rows:return None
    rows.sort(key=lambda j:float(j.get("created_at",0) or 0),reverse=True)
    return rows[0]


def smart_finder_status():
    j=_finder_job_latest()
    if j:return j
    st=load_json(SCAN_FILE,{})
    return {"action":"finder","status":"idle","id":"","percent":0,"detail":"Smart Finder is idle","queries_done":0,"query_limit":0,"cursor":int(st.get("smart_finder:cursor",0) or 0),"matrix_total":len(smart_finder_matrix()),"new_candidates":0,"google_hits":0,"noise_blocked":0,"qualified":0,"filtered":0,"waiting":0,"workers":3}


def _finder_cloud_lock_path():
    c=cfg();folder=_sync_folder(c) if c.get("sync_enabled") else None
    return (folder/"runtime"/"smart-finder-lock.json") if folder else None


def _finder_lock_acquire():
    p=_finder_cloud_lock_path()
    if not p:return
    p.parent.mkdir(parents=True,exist_ok=True)
    old=load_json(p,{})
    try:age=time.time()-float(old.get("ts",0) or 0)
    except Exception:age=9999
    c=cfg();own=c.get("sync_device_id")
    if old.get("device_id") and old.get("device_id")!=own and age<120:
        raise RuntimeError(f"Smart Finder is already running on {old.get('device_name') or 'your other computer'}. Let that device run it; OneDrive will sync the results here.")
    _write_atomic(p,json.dumps({"device_id":own,"device_name":c.get("sync_device_name","This computer"),"ts":time.time(),"version":APP_VERSION},ensure_ascii=False))


def _finder_lock_touch():
    p=_finder_cloud_lock_path()
    if not p:return
    c=cfg()
    try:_write_atomic(p,json.dumps({"device_id":c.get("sync_device_id"),"device_name":c.get("sync_device_name","This computer"),"ts":time.time(),"version":APP_VERSION},ensure_ascii=False))
    except Exception:pass


def _finder_lock_release():
    p=_finder_cloud_lock_path()
    if not p or not p.exists():return
    try:
        old=load_json(p,{})
        if old.get("device_id")==cfg().get("sync_device_id"):p.unlink()
    except Exception:pass


def discover_google_smart(sector,area,term,pages=1):
    """Finder discovery call returning concrete prospect ids for the concurrent qualification queue."""
    key=cfg().get("google_places_key")
    if not key:raise RuntimeError("Google Places API key is not configured.")
    q=f"{term} in {area}, United Kingdom"
    # Smart Finder intentionally uses Core/Pro discovery. Website/phone is fetched only for candidates that survive filtering.
    ps=google_text(q,key,max(1,min(int(pages),3)),"pro")
    raw=[gp_to_lead(p,sector,f"Smart Finder: {term} | {area}") for p in ps]
    accepted=[];blocked=[]
    for lead in raw:
        reason=hard_noise_reason(lead)
        if reason:blocked.append({"company":lead.get("company"),"reason":reason})
        else:accepted.append(lead)
    r=upsert(accepted)
    ids=[]
    for x in (r.get("added_ids") or [])+(r.get("merged_ids") or []):
        if x and x not in ids:ids.append(x)
    log("smart_finder_google",{"sector":sector,"area":area,"term":term,"found":len(ps),"usable":len(accepted),"noise_blocked":len(blocked),"blocked_examples":blocked[:5],**{k:v for k,v in r.items() if not k.endswith('_ids')}})
    return {"query":q,"found":len(ps),"usable":len(accepted),"noise_blocked":len(blocked),"candidate_ids":ids,**r}


def _process_pipeline_lead(id_, job_id="", company_index=0, total=0):
    """Shared one-company Smart Pipeline used by manual batches and Smart Finder."""
    l=get_lead(id_);company=(l or {}).get("company") or "Prospect"
    if not l:raise SkipProspect("Prospect record was not found")
    done,why=_action_complete(l,"pipeline")
    if done: return {"status":"already","reason":why,"company":company}
    if hard_noise_reason(l) or l.get("discovery_excluded"):
        raise SkipProspect(l.get("discovery_exclusion_reason") or "Obvious non-industrial / irrelevant result")
    if not l.get("ai"):
        if not l.get("website"):
            if l.get("place_id"):
                key=cfg().get("google_places_key")
                if not key:raise SkipProspect("No website saved and Google Places is not configured")
                if job_id:_job_set(job_id,detail=f"Finding website • {company}",company=company,current_url="")
                p2=google_details(l["place_id"],key,"enterprise")
                def apply_google_pipe(x):merge_into(x,gp_to_lead(p2,x.get("sector",""),"Google enterprise enrichment"));return dict(x)
                update_lead(id_,apply_google_pipe)
            else:raise SkipProspect("No website or Google Place match")
        l=get_lead(id_) or l
        if not l.get("website"):raise SkipProspect("No company website found")
        ev=l.get("web_evidence") or {}
        if not ev.get("text"):
            def pipe_progress(page_index,page_total,message,current_url,pages_found):
                if job_id:_job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company)
            if job_id:_job_set(job_id,detail=f"Reading website evidence • {company}",company=company,current_url=l.get("website",""))
            def pipe_enrich(x):
                ev2=web_enrich(x,pipe_progress);x["web_evidence"]=ev2;x["emails"]=merge_lists(x.get("emails",[]),ev2.get("emails",[]))
                if ev2.get("contact_page"):x["contact_page"]=ev2["contact_page"]
                if ev2.get("linkedin_url"):x["linkedin_url"]=ev2["linkedin_url"]
                x.pop("web_skip_reason",None);return ev2
            ev=update_lead(id_,pipe_enrich) or {}
            if not ev.get("text"):
                update_lead(id_,lambda x:(x.update({"web_skip_reason":"No usable website pages found","ai_skip_reason":"No usable website evidence"}) or True))
                raise SkipProspect("No usable website evidence")
        # V4.2: deterministic evidence filter BEFORE OpenAI spend.
        gate=apply_website_relevance_gate(id_)
        if not gate.get("pass"):
            update_lead(id_,lambda x:(x.update({"ai_skip_reason":"Filtered before AI — "+str(gate.get("reason") or "not relevant")}) or True))
            raise SkipProspect("Filtered before AI — "+str(gate.get("reason") or "not relevant"))
        l=get_lead(id_) or l
        if job_id:_job_set(job_id,detail=f"AI qualifying • {company}",company=company,current_url=l.get("website",""))
        result=_ai_with_retry(job_id,l,0,0,company)
        if job_id:_job_set(job_id,detail=f"Saving priority + email draft • {company}",company=company)
        def pipe_save_ai(x):x["ai"]=result;x.pop("ai_skip_reason",None);return result
        update_lead(id_,pipe_save_ai)
    current=get_lead(id_) or {}
    if cfg().get("auto_capsule_high_priority",False) and cfg().get("capsule_token") and current.get("outreach_priority_code") in ("P1","P2") and not (current.get("capsule") or {}).get("capsule_id"):
        if job_id:_job_set(job_id,detail=f"Sending high-priority prospect to Capsule • {company}",company=company,current_url="")
        update_lead(id_,lambda x:(x.update({"capsule":capsule_sync(x)}) or x["capsule"]))
    return {"status":"done","company":company}


def _run_smart_finder(job_id):
    job=_job_get(job_id) or {}
    awake=_begin_unattended_mode();awake_ok=bool(awake[1])
    matrix=smart_finder_matrix();matrix_total=len(matrix)
    query_limit=max(1,min(int(job.get("query_limit",100) or 100),1000))
    pages=max(1,min(int(job.get("pages",1) or 1),3))
    workers=max(1,min(int(job.get("workers",3) or 3),4))
    st=load_json(SCAN_FILE,{})
    cursor=int(st.get("smart_finder:cursor",0) or 0)
    if cursor>=matrix_total:cursor=0
    queries_done=int(job.get("queries_done",0) or 0)
    google_hits=int(job.get("google_hits",0) or 0);noise_blocked=int(job.get("noise_blocked",0) or 0)
    new_candidates=int(job.get("new_candidates",0) or 0);qualified=int(job.get("qualified",0) or 0);filtered=int(job.get("filtered",0) or 0);skipped=int(job.get("skipped",0) or 0)
    processed=set(job.get("processed_ids") or [])
    pending=[];queued=set(processed)
    for x in (job.get("pending_ids") or []):
        if x and x not in queued:pending.append(x);queued.add(x)
    # Seed a small existing backlog so AI/crawling starts immediately while Google continues discovering.
    if not pending and queries_done==0:
        arr=leads()
        for l in arr:
            done,_=_action_complete(l,"pipeline")
            if not done and not l.get("discovery_excluded") and l.get("id") and l.get("id") not in queued:
                pending.append(l["id"]);queued.add(l["id"])
                if len(pending)>=20:break
        job["backlog_seeded"]=len(pending)
    inflight={};fatal=None;stop_requested=False

    def persist(detail=None,company=None,current_url=None,status="running"):
        discovery_fraction=min(1,queries_done/max(1,query_limit))
        # Discovery owns 90% of the bar; final queue draining owns the last 10%.
        if queries_done<query_limit:
            pct=min(89.5,discovery_fraction*90)
        else:
            work_total=max(1,qualified+filtered+skipped+len(pending)+len(inflight))
            pct=90+10*((qualified+filtered+skipped)/work_total)
        _job_set(job_id,status=status,percent=min(99.5,pct) if status=="running" else pct,
                 detail=detail or f"Finding + qualifying • {queries_done}/{query_limit} searches",
                 company=company or "",current_url=current_url or "",queries_done=queries_done,query_limit=query_limit,
                 cursor=cursor,matrix_total=matrix_total,google_hits=google_hits,noise_blocked=noise_blocked,new_candidates=new_candidates,
                 qualified=qualified,filtered=filtered,skipped=skipped,waiting=len(pending),active_workers=len(inflight),workers=workers,
                 completed=queries_done,total=query_limit,remaining=max(0,query_limit-queries_done),pending_ids=list(pending),processed_ids=list(processed),
                 awake_protected=awake_ok,checkpointed=True,last_update_epoch=time.time())

    try:
        _finder_lock_acquire()
        persist("Starting Smart Finder • seeding the AI pipeline")
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix="yms-finder-pipeline") as ex:
            while True:
                cur=_job_get(job_id) or {}
                stop_requested=bool(cur.get("stop_requested"))
                # Fill free AI/evidence worker slots. A user stop does not start more queued work.
                while not stop_requested and not fatal and pending and len(inflight)<workers:
                    id_=pending.pop(0)
                    if id_ in processed:continue
                    l=get_lead(id_);done,_=_action_complete(l,"pipeline")
                    if done:processed.add(id_);continue
                    fut=ex.submit(_process_pipeline_lead,id_,job_id,0,0)
                    inflight[fut]=id_
                # Continue finding while pipeline workers are busy, but cap backlog to avoid runaway API queues.
                if not stop_requested and not fatal and queries_done<query_limit and len(pending)+len(inflight)<36:
                    sector,area,term=matrix[cursor]
                    persist(f"Searching {sector} • {area} • {term}")
                    try:
                        r=discover_google_smart(sector,area,term,pages)
                    except Exception as ex2:
                        fatal=(ex2,"google")
                    else:
                        google_hits+=int(r.get("found",0) or 0);noise_blocked+=int(r.get("noise_blocked",0) or 0)
                        candidate_ids=r.get("candidate_ids") or []
                        for id_ in candidate_ids:
                            if id_ in queued:continue
                            l=get_lead(id_);done,_=_action_complete(l,"pipeline")
                            if done:queued.add(id_);continue
                            pending.append(id_);queued.add(id_);new_candidates+=1
                        queries_done+=1;cursor=(cursor+1)%matrix_total
                        st=load_json(SCAN_FILE,{});st["smart_finder:cursor"]=cursor;save_json(SCAN_FILE,st)
                        _finder_lock_touch()
                        persist(f"Found {r.get('usable',0)} usable • {r.get('noise_blocked',0)} obvious noise blocked • pipeline running")
                # Collect finished pipeline work without blocking discovery unnecessarily.
                finished=[f for f in list(inflight) if f.done()]
                for fut in finished:
                    id_=inflight.pop(fut);processed.add(id_);l=get_lead(id_) or {};company=l.get("company") or "Prospect"
                    try:
                        rr=fut.result()
                        if rr.get("status")=="done":qualified+=1
                    except SkipProspect as ex2:
                        reason=str(ex2)
                        if "Filtered before AI" in reason or (get_lead(id_) or {}).get("discovery_excluded"):filtered+=1
                        else:skipped+=1
                        update_lead(id_,lambda x:(x.update({"ai_skip_reason":reason[:240]}) or True))
                    except Exception as ex2:
                        kind=_service_failure_kind("pipeline",ex2)
                        if kind=="ai_response":
                            skipped+=1;update_lead(id_,lambda x:(x.update({"ai_skip_reason":"AI response failed after automatic retries"}) or True))
                        else:
                            fatal=(ex2,kind)
                    persist(f"Pipeline saved • {company}",company=company)
                if fatal:
                    # Let already-running workers finish/checkpoint, but do not discover or start new work.
                    if inflight:
                        time.sleep(.18);continue
                    break
                if stop_requested:
                    if inflight:
                        time.sleep(.18);continue
                    break
                if queries_done>=query_limit and not pending and not inflight:break
                if not finished and (queries_done>=query_limit or len(pending)+len(inflight)>=36):time.sleep(.16)
        if fatal:
            ex2,kind=fatal
            msg="Smart Finder paused safely"
            if kind=="quota":msg="Smart Finder paused — OpenAI credit/quota exhausted"
            elif kind=="auth":msg="Smart Finder paused — API authentication failed"
            elif kind in ("temporary","rate_limit"):msg="Smart Finder paused — service/network problem after retries"
            _job_set(job_id,status="paused",resumable=True,failure_kind=kind,error=str(ex2),detail=f"{msg} • everything completed is saved",finished_at=time.time(),pending_ids=list(pending),processed_ids=list(processed),queries_done=queries_done,query_limit=query_limit,google_hits=google_hits,noise_blocked=noise_blocked,new_candidates=new_candidates,qualified=qualified,filtered=filtered,skipped=skipped,waiting=len(pending),active_workers=0,awake_protected=False)
        else:
            stopped=stop_requested
            detail=(f"Stopped safely • {queries_done} searches • {qualified} qualified • {filtered} filtered before AI • {len(pending)} discovered prospects left for later" if stopped else f"Complete • {queries_done} searches • {qualified} qualified • {filtered} filtered before AI • {noise_blocked} obvious noise blocked")
            _job_set(job_id,status="complete",percent=100,resumable=False,detail=detail,finished_at=time.time(),queries_done=queries_done,query_limit=query_limit,google_hits=google_hits,noise_blocked=noise_blocked,new_candidates=new_candidates,qualified=qualified,filtered=filtered,skipped=skipped,waiting=len(pending),active_workers=0,pending_ids=list(pending),processed_ids=list(processed),completed=query_limit if not stopped else queries_done,total=query_limit,remaining=0 if not stopped else max(0,query_limit-queries_done),awake_protected=False,stopped=stopped)
    except Exception as ex2:
        _job_set(job_id,status="paused",resumable=True,error=str(ex2),failure_kind=_service_failure_kind("pipeline",ex2),detail="Smart Finder paused safely — all completed prospect work is saved",finished_at=time.time(),pending_ids=list(pending),processed_ids=list(processed),awake_protected=False)
    finally:
        _finder_lock_release();_end_unattended_mode(awake)


def start_smart_finder(query_limit=100,pages=1):
    c=cfg()
    if c.get("free_mode",True):raise RuntimeError("Smart Finder needs Full Mode because it automatically AI-qualifies relevant companies. Switch Full Mode on in Settings first.")
    if not c.get("google_places_key"):raise RuntimeError("Google Places is not configured.")
    if not c.get("openai_key"):raise RuntimeError("OpenAI is not configured.")
    latest=_finder_job_latest()
    if latest and latest.get("status") in ("queued","running"):
        return latest
    if latest and latest.get("status")=="paused" and latest.get("resumable"):
        raise RuntimeError("A Smart Finder session is paused with saved work. Resume it from the activity panel instead of starting a new one.")
    limit=max(1,min(int(query_limit or 100),1000));pages=max(1,min(int(pages or 1),3));job_id=uuid.uuid4().hex
    with JOB_LOCK:
        JOBS[job_id]={"id":job_id,"action":"finder","ids":[],"status":"queued","percent":0,"detail":"Smart Finder queued","query_limit":limit,"queries_done":0,"pages":pages,"workers":3,"google_hits":0,"noise_blocked":0,"new_candidates":0,"qualified":0,"filtered":0,"skipped":0,"waiting":0,"active_workers":0,"pending_ids":[],"processed_ids":[],"stop_requested":False,"completed":0,"total":limit,"remaining":limit,"created_at":time.time(),"updated_at":time.time(),"error":"","failure_kind":"","resumable":False,"awake_protected":False,"checkpointed":True}
        _persist_jobs_locked()
    threading.Thread(target=_run_smart_finder,args=(job_id,),daemon=True).start()
    return _job_get(job_id)


def stop_smart_finder():
    j=_finder_job_latest()
    if not j or j.get("status") not in ("queued","running"):
        return {"ok":True,"message":"Smart Finder is not currently running.",**(j or smart_finder_status())}
    _job_set(j["id"],stop_requested=True,detail="Stopping discovery safely • finishing current pipeline work")
    return {"ok":True,"message":"Stop requested. No new searches will start; current company work will checkpoint safely.",**(_job_get(j["id"]) or {})}
'''


def patch_server(path:Path):
    s=path.read_text('utf-8')
    s=re.sub(r'APP_VERSION\s*=\s*"[^"]+"','APP_VERSION = "4.2.0"',s,count=1)
    # Add new config defaults/masked values.
    s=s.replace('    c.setdefault("hide_noise_by_default", True)\n', '    c.setdefault("hide_noise_by_default", True)\n    c.setdefault("smart_finder_query_limit", 100)\n    c.setdefault("smart_finder_pages", 1)\n')
    s=s.replace('        "hide_noise_by_default":bool(c.get("hide_noise_by_default",True)),\n', '        "hide_noise_by_default":bool(c.get("hide_noise_by_default",True)),\n        "smart_finder_query_limit":int(c.get("smart_finder_query_limit",100) or 100),\n        "smart_finder_pages":int(c.get("smart_finder_pages",1) or 1),\n')
    # Expand obvious hard-noise category list and chains safely.
    s=s.replace('    "clothing_store","shoe_store","jewelry_store","book_store","pet_store"\n}', '    "clothing_store","shoe_store","jewelry_store","book_store","pet_store",\n    "shopping_mall","gas_station","car_dealer","car_rental","car_wash","parking",\n    "tourist_attraction","museum","library","place_of_worship"\n}')
    s=s.replace('    ("Wetherspoon", r"\\bwetherspoons?\\b|\\bj\\.?d\\.? wetherspoon\\b"),\n]', '    ("Wetherspoon", r"\\bwetherspoons?\\b|\\bj\\.?d\\.? wetherspoon\\b"),\n    ("B&Q", r"\\bb\\s*&\\s*q\\b"), ("IKEA", r"\\bikea\\b"), ("Halfords", r"\\bhalfords\\b"),\n    ("Primark", r"\\bprimark\\b"), ("Poundland", r"\\bpoundland\\b"), ("Home Bargains", r"\\bhome bargains\\b"),\n]')
    # upsert returns concrete ids for Finder queue.
    s=s.replace('        all_leads=load_json(LEADS_FILE,[]);added=merged=0\n', '        all_leads=load_json(LEADS_FILE,[]);added=merged=0;added_ids=[];merged_ids=[]\n',1)
    s=s.replace('                merge_into(cand,n);merged+=1\n', '                merge_into(cand,n);merged+=1\n                if cand.get("id") and cand.get("id") not in merged_ids:merged_ids.append(cand.get("id"))\n',1)
    s=s.replace('                all_leads.append(n);added+=1\n', '                all_leads.append(n);added+=1\n                if n.get("id"):added_ids.append(n.get("id"))\n',1)
    s=s.replace('        return {"added":added,"merged":merged,"total":len(all_leads)}\n', '        return {"added":added,"merged":merged,"total":len(all_leads),"added_ids":added_ids,"merged_ids":merged_ids}\n',1)
    # Insert V4.2 block immediately before progress job action completeness.
    marker='def _action_complete(l, action):\n'
    if marker not in s: raise RuntimeError('server marker action complete missing')
    s=s.replace(marker,SERVER_INSERT+'\n\n'+marker,1)
    # Remove inner SkipProspect declaration; now global.
    s=s.replace('    class SkipProspect(Exception):pass\n','',1)
    # Replace existing pipeline implementation with shared helper.
    start='        if action=="pipeline":\n            # One-click YMS workflow: website -> evidence -> AI -> priority/draft -> optional Capsule.\n'
    end='            return {"status":"done","id":id_,"company":company,"pos":work_pos}\n\n        if action=="ai":\n'
    a=s.find(start)
    b=s.find(end,a)
    if a<0 or b<0: raise RuntimeError('pipeline block not found')
    replacement='        if action=="pipeline":\n            rr=_process_pipeline_lead(id_,job_id,min(selected_total,already_done+work_pos+1),selected_total)\n            return {"status":rr.get("status","done"),"id":id_,"company":company,"pos":work_pos}\n\n        if action=="ai":\n'
    s=s[:a]+replacement+s[b+len(end):]
    # Finder resume route in generic job resume.
    old='    threading.Thread(target=_run_progress_job,args=(job_id,action,ids),daemon=True).start();return _job_get(job_id)\n'
    new='    if action=="finder":threading.Thread(target=_run_smart_finder,args=(job_id,),daemon=True).start()\n    else:threading.Thread(target=_run_progress_job,args=(job_id,action,ids),daemon=True).start()\n    return _job_get(job_id)\n'
    if old not in s: raise RuntimeError('resume marker missing')
    s=s.replace(old,new,1)
    # GET finder status.
    s=s.replace('            if p=="/api/job/recent":\n                self.sendj(_job_recent() or {});return\n', '            if p=="/api/job/recent":\n                self.sendj(_job_recent() or {});return\n            if p=="/api/finder/status":\n                self.sendj(smart_finder_status());return\n',1)
    # Save finder settings.
    s=s.replace('                if "hide_noise_by_default" in b:c["hide_noise_by_default"]=bool(b.get("hide_noise_by_default"))\n', '                if "hide_noise_by_default" in b:c["hide_noise_by_default"]=bool(b.get("hide_noise_by_default"))\n                if "smart_finder_query_limit" in b:c["smart_finder_query_limit"]=max(1,min(int(b.get("smart_finder_query_limit") or 100),1000))\n                if "smart_finder_pages" in b:c["smart_finder_pages"]=max(1,min(int(b.get("smart_finder_pages") or 1),3))\n',1)
    # POST finder routes before regular jobs.
    s=s.replace('            if p=="/api/job/start":\n', '            if p=="/api/finder/start":\n                self.sendj(start_smart_finder(b.get("query_limit",cfg().get("smart_finder_query_limit",100)),b.get("pages",cfg().get("smart_finder_pages",1))));return\n            if p=="/api/finder/stop":\n                self.sendj(stop_smart_finder());return\n            if p=="/api/job/start":\n',1)
    path.write_text(s,'utf-8')

CSS_INSERT=r'''
.finderCard{border-color:rgba(243,106,50,.30)!important;background:radial-gradient(circle at 85% 0,rgba(243,106,50,.13),transparent 34%),linear-gradient(180deg,#0d1c28,#081721)!important}
.finderTop{display:flex;justify-content:space-between;align-items:flex-start;gap:18px}.finderTop h2{margin:5px 0 7px;font-size:23px;letter-spacing:-.03em}.finderControls{display:grid;grid-template-columns:150px 150px auto auto;gap:8px;align-items:end;min-width:min(100%,620px)}
.finderMetrics{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:13px}.finderMetric{border:1px solid var(--line);background:rgba(4,14,22,.55);border-radius:11px;padding:10px 11px}.finderMetric b{display:block;font-size:18px;letter-spacing:-.035em}.finderMetric span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.08em;margin-top:4px}.finderState{display:flex;align-items:center;gap:7px;color:#a9bbc8;font-size:10px;margin-top:10px}.finderDot{width:7px;height:7px;border-radius:50%;background:#617789}.finderDot.live{background:var(--green);box-shadow:0 0 12px rgba(75,214,160,.45);animation:progressPulse 1.3s infinite}.finderDot.paused{background:var(--amber)}
@media(max-width:1100px){.finderTop{display:block}.finderControls{margin-top:13px}.finderMetrics{grid-template-columns:repeat(3,1fr)}}@media(max-width:720px){.finderControls{grid-template-columns:1fr 1fr}.finderMetrics{grid-template-columns:1fr 1fr}}
'''

FINDER_DASH=r'''
<div class="card finderCard" id="finderDashCard"><div class="finderTop"><div><div class="ey">SMART FINDER • V4.2</div><h2>Find and qualify new YMS prospects at the same time.</h2><p class="muted small" style="max-width:790px">Rotates through every YMS sector and UK area, blocks obvious consumer noise before crawling, checks website relevance before OpenAI, then grades, prioritises and drafts the outreach while discovery carries on.</p></div><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" id="finderDashStart" onclick="startSmartFinder(true)">Start Smart Finder</button><button class="btn" id="finderDashStop" onclick="stopSmartFinder()" disabled>Stop safely</button><button class="btn" onclick="showById('discover')">Finder controls</button></div></div><div class="finderMetrics"><div class="finderMetric"><b id="fdQueries">0</b><span>Searches</span></div><div class="finderMetric"><b id="fdHits">0</b><span>Google hits</span></div><div class="finderMetric"><b id="fdNew">0</b><span>New candidates</span></div><div class="finderMetric"><b id="fdFiltered">0</b><span>Filtered before AI</span></div><div class="finderMetric"><b id="fdAI">0</b><span>Qualified</span></div><div class="finderMetric"><b id="fdWaiting">0</b><span>Pipeline waiting</span></div></div><div class="finderState"><span id="finderDashDot" class="finderDot"></span><span id="finderDashText">Smart Finder is idle.</span></div></div>
'''

FINDER_DISCOVER=r'''
<div class="card s12 finderCard" id="finderControlCard"><div class="finderTop"><div><div class="ey">AUTOMATED ENGINE • ALL SECTORS</div><h2>Smart Finder</h2><p class="muted small" style="max-width:820px">One background run mixes Switchgear, Enclosures, Fabrication, Lifting, Marine, Data Centres, Tool Hire, Pipe/Process and General Engineering. Discovery and the 3-worker qualification pipeline run concurrently. Existing prospects and completed work are skipped automatically.</p></div><div class="finderControls"><div class="field" style="margin:0"><label>Google searches this run</label><select id="finderQueries"><option>25</option><option>50</option><option selected>100</option><option>250</option><option>500</option></select></div><div class="field" style="margin:0"><label>Pages per search</label><select id="finderPages"><option selected>1</option><option>2</option><option>3</option></select></div><button class="btn primary" id="finderStartBtn" onclick="startSmartFinder(false)">Start Finder</button><button class="btn" id="finderStopBtn" onclick="stopSmartFinder()" disabled>Stop safely</button></div></div><div class="finderMetrics"><div class="finderMetric"><b id="fcQueries">0</b><span>Searches</span></div><div class="finderMetric"><b id="fcHits">0</b><span>Google hits</span></div><div class="finderMetric"><b id="fcNew">0</b><span>New candidates</span></div><div class="finderMetric"><b id="fcNoise">0</b><span>Obvious noise</span></div><div class="finderMetric"><b id="fcFiltered">0</b><span>Website filtered</span></div><div class="finderMetric"><b id="fcAI">0</b><span>AI qualified</span></div></div><div id="finderControlText" class="notice good" style="margin-top:11px"><b>Idle.</b> Smart Finder only sends a company to OpenAI after it survives the Google noise filter and the website relevance gate.</div></div>
'''

JS_INSERT=r'''
let finderLastStatus=null;
function finderNum(id,v){if($(id))$(id).textContent=Number(v||0).toLocaleString()}
function paintFinderStatus(j){j=j||{};finderLastStatus=j;let running=j.status==="running"||j.status==="queued",paused=j.status==="paused";let q=Number(j.queries_done||0),limit=Number(j.query_limit||0);finderNum("fdQueries",limit?`${q}/${limit}`:q);finderNum("fcQueries",limit?`${q}/${limit}`:q);finderNum("fdHits",j.google_hits);finderNum("fcHits",j.google_hits);finderNum("fdNew",j.new_candidates);finderNum("fcNew",j.new_candidates);finderNum("fdFiltered",j.filtered);finderNum("fcFiltered",j.filtered);finderNum("fcNoise",j.noise_blocked);finderNum("fdAI",j.qualified);finderNum("fcAI",j.qualified);finderNum("fdWaiting",j.waiting);["finderDashStart","finderStartBtn"].forEach(id=>{if($(id)){$(id).disabled=running||paused;$(id).style.opacity=(running||paused)?".5":"1"}});["finderDashStop","finderStopBtn"].forEach(id=>{if($(id))$(id).disabled=!running});let text=j.detail||"Smart Finder is idle.";if($("finderDashText"))$("finderDashText").textContent=text;if($("finderControlText")){$("finderControlText").innerHTML=`<b>${esc((j.status||"idle").toUpperCase())}</b> • ${esc(text)}${running?` • ${Number(j.active_workers||0)} active pipeline workers • ${Number(j.waiting||0)} waiting`:""}`;$("finderControlText").className=paused?"notice warn":running?"notice good":"notice"}[["finderDashDot",running,paused]].forEach(([id,live,p])=>{if($(id))$(id).className="finderDot"+(live?" live":p?" paused":"")});if($("finderQueries")&&document.activeElement!==$("finderQueries")&&conf.smart_finder_query_limit)$("finderQueries").value=String(conf.smart_finder_query_limit);if($("finderPages")&&document.activeElement!==$("finderPages")&&conf.smart_finder_pages)$("finderPages").value=String(conf.smart_finder_pages)}
async function refreshFinderStatus(){try{let j=await api("/api/finder/status");paintFinderStatus(j)}catch(e){}}
async function startSmartFinder(fromDashboard=false){if(conf.free_mode){toast("Smart Finder needs Full Mode because it automatically runs GPT-5 nano qualification after the relevance gates.","warn",6500);showById("settings");return}let limit=Number($("finderQueries")?.value||conf.smart_finder_query_limit||100),pages=Number($("finderPages")?.value||conf.smart_finder_pages||1);if(fromDashboard){limit=Number(conf.smart_finder_query_limit||100);pages=Number(conf.smart_finder_pages||1)}if(!confirm(`Start Smart Finder?\n\n${limit} Google searches across ALL YMS sectors. Discovery and qualification will run together in the background. Obvious noise and weak website matches are filtered before OpenAI.`))return;try{let j=await api("/api/finder/start",{query_limit:limit,pages});paintFinderStatus(j);showProgress("Smart Finder • all YMS sectors",j.created_at||0);activeProgressJobId=j.id;paintJob(j);pollProgressJob(j.id)}catch(e){toast(e.message,"bad",7500)}}
async function stopSmartFinder(){try{let j=await api("/api/finder/stop",{});paintFinderStatus(j);toast(j.message||"Stop requested.","good",5000)}catch(e){toast(e.message,"bad",6000)}}
'''


def patch_html(path:Path, platform:str):
    s=path.read_text('utf-8')
    s=re.sub(r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>',f'<title>YMS Prospect Finder V4.2.0 {platform} — YMS-Tools</title>',s,count=1)
    s=re.sub(r'<b id="versionLabel">Prospect Finder V[^<]+</b>',f'<b id="versionLabel">Prospect Finder V4.2.0 {platform}</b>',s,count=1)
    # CSS before closing style.
    s=s.replace('\n</style></head>', '\n'+CSS_INSERT+'\n</style></head>',1)
    # Dashboard smart finder card after hero.
    hero_end='</div></div></div>\n<div class="v4Queue">'
    if hero_end not in s: raise RuntimeError('dashboard hero end missing')
    s=s.replace(hero_end,'</div></div></div>\n'+FINDER_DASH+'\n<div class="v4Queue">',1)
    # Discover finder card immediately inside grid.
    s=s.replace('<section id="discover" class="view">\n<div class="grid">','<section id="discover" class="view">\n<div class="grid">\n'+FINDER_DISCOVER,1)
    # Settings automation explanation.
    s=s.replace('<div class="notice good"><b>Always automatic:</b> live list refresh, Mac ↔ Windows sync polling, duplicate prevention, completed-scan skipping, per-company safe checkpoints, personalised email drafting and resumable background jobs.</div>', '<div class="notice good"><b>Always automatic:</b> live list refresh, Mac ↔ Windows sync polling, duplicate prevention, completed-scan skipping, per-company safe checkpoints, personalised email drafting, resumable jobs and V4.2 website relevance filtering before AI.</div>',1)
    # Add finder default controls to automation card by inserting a small row after hide-noise toggle.
    target='<div class="toggleRow"><div><b>Hide obvious noise by default</b><span>Keeps supermarkets, restaurants and other rejected consumer results out of your normal sales queue.</span></div><select id="hideNoiseDefault" class="switchSelect"><option value="true">ON</option><option value="false">OFF</option></select></div>'
    repl=target+'<div class="toggleRow"><div><b>Smart Finder default run</b><span>Used by the one-click Dashboard button. You can override these from Discover.</span></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;min-width:210px"><select id="finderQueriesSetting" class="switchSelect"><option>25</option><option>50</option><option>100</option><option>250</option><option>500</option></select><select id="finderPagesSetting" class="switchSelect"><option>1</option><option>2</option><option>3</option></select></div></div>'
    if target not in s: raise RuntimeError('noise setting target missing')
    s=s.replace(target,repl,1)
    # Update version badges/text.
    s=s.replace('id="updateSettingsBadge">V4.1<','id="updateSettingsBadge">V4.2<')
    s=s.replace('pointing at this V4.1.0 folder','pointing at this V4.2.0 folder')
    # JS insert after helper constants.
    marker='function show(id,b){'
    if marker not in s: raise RuntimeError('JS show marker missing')
    s=s.replace(marker,JS_INSERT+'\n'+marker,1)
    # boot includes finder poll.
    s=s.replace('refreshUpdateStatus(false);setInterval(refreshSyncStatus,5000);setInterval(refreshLeadsIfChanged,2000)', 'refreshUpdateStatus(false);refreshFinderStatus();setInterval(refreshSyncStatus,5000);setInterval(refreshLeadsIfChanged,2000);setInterval(refreshFinderStatus,2000)',1)
    # paintJob special Finder metrics.
    old='function paintJob(j){activeProgressLatestJob=j;let completed=Number(j.completed)||0;'
    if old not in s: raise RuntimeError('paintJob marker missing')
    s=s.replace(old,'function paintJob(j){activeProgressLatestJob=j;if(j.action==="finder")paintFinderStatus(j);let completed=Number(j.completed)||0;',1)
    # Replace progress count construction for finder via injection before setting text.
    old2='$("progressCount").textContent=parts.join(" • ");'
    new2='if(j.action==="finder")parts=[`${j.queries_done||0}/${j.query_limit||0} searches`,`${j.google_hits||0} Google hits`,`${j.noise_blocked||0} obvious noise`,`${j.filtered||0} filtered before AI`,`${j.qualified||0} qualified`,`${j.waiting||0} waiting`];$("progressCount").textContent=parts.join(" • ");'
    if old2 not in s: raise RuntimeError('progress count missing')
    s=s.replace(old2,new2,1)
    # Finder completion message in poller.
    # Legacy blocking progress helper does not handle Finder; Finder uses the background job panel.
    # restore title mapping.
    old4='let title=j.action==="ai"?`AI qualification • ${j.total||0} selected`:j.action==="web"?"Bulk website evidence crawl":"Companies House matching";'
    new4='let title=j.action==="finder"?"Smart Finder • all YMS sectors":j.action==="pipeline"?`r"?"Sm,uerif