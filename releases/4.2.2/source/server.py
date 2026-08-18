#!/usr/bin/env python3
"""YMS Prospect Finder V4.2.2 — stability + Facebook fallback update.

Patches the currently installed V4.2.1 app from the updater's safe backup.
Changes:
- Facebook business-page fallback when no normal website can be found.
- Longer transient HTTP/OpenAI retry/backoff (including 503).
- Smart Finder Stop becomes a resumable pause.
- Smart Finder resume works even though Finder jobs do not use a normal ids queue.
- Starting Finder while a saved Finder is paused automatically resumes it.
- Explicit Resume Smart Finder controls and paused-job progress handling.
- Clear status messages instead of silent dead ends.
"""
import os, re, sys, time, shutil
from pathlib import Path

TARGET_VERSION = "4.2.2"
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


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"V4.2.2 could not locate {label}. The old app was left intact.")
    return text.replace(old, new, 1)


def replace_between(text, start, end, replacement, label):
    a = text.find(start)
    b = text.find(end, a + len(start)) if a >= 0 else -1
    if a < 0 or b < 0:
        raise RuntimeError(f"V4.2.2 could not locate {label}. The old app was left intact.")
    return text[:a] + replacement + text[b:]


PRESENCE_HELPERS = r'''
# ---------------------------------------------------------------------------
# V4.2.2 resilient web-presence fallback
# ---------------------------------------------------------------------------
def _is_facebook_url(url):
    try:
        h=(urlparse(url or "").netloc or "").lower()
        return h=="facebook.com" or h.endswith(".facebook.com") or h=="fb.com" or h.endswith(".fb.com")
    except Exception:return False


def _facebook_candidate_url(href):
    href=unescape((href or "").strip())
    if not href:return ""
    if href.startswith("//"):href="https:"+href
    try:
        p=urlparse(href)
        if "duckduckgo.com" in (p.netloc or "").lower():
            q=parse.parse_qs(p.query)
            href=(q.get("uddg") or [""])[0]
            href=parse.unquote(href)
        p=urlparse(href)
        host=(p.netloc or "").lower()
        if not (host=="facebook.com" or host.endswith(".facebook.com") or host=="fb.com" or host.endswith(".fb.com")):return ""
        low=(p.path or "").lower()
        if any(x in low for x in ("/login","/help","/marketplace","/watch","/reel","/share","/groups/","/events/","/photo")):return ""
        return ("https://"+(p.netloc or "www.facebook.com")+(p.path or "/")).rstrip("/")
    except Exception:return ""


def _transient_call(label, fn, job_id="", company="", attempts=4):
    delays=(2,5,12,25)
    last=None
    for n in range(1,max(2,int(attempts))+1):
        try:return fn()
        except Exception as ex:
            last=ex;kind=_service_failure_kind("pipeline",ex)
            msg=str(ex).lower()
            transient=(kind in ("temporary","rate_limit") or "http 408" in msg or "http 429" in msg or "service unavailable" in msg or "bad gateway" in msg or "gateway timeout" in msg)
            if not transient or n>=attempts:raise
            delay=delays[min(n-1,len(delays)-1)]
            if job_id:_job_set(job_id,detail=f"Temporary {label} issue — retrying in {delay}s • {company}",company=company,failure_kind=kind)
            time.sleep(delay)
    raise last


def find_facebook_fallback(l, job_id="", company=""):
    """Find a likely public Facebook business page using a lightweight web-search fallback."""
    if not isinstance(l,dict):return {"found":False,"reason":"Invalid prospect"}
    existing=l.get("facebook_url") or ""
    if existing:return {"found":True,"url":existing,"title":l.get("facebook_title","") or l.get("company","")}
    if _is_facebook_url(l.get("website")):
        return {"found":True,"url":l.get("website"),"title":l.get("company","")}
    company_name=(l.get("company") or "").strip()
    if not company_name:return {"found":False,"reason":"No company name"}
    loc=(l.get("postcode") or l.get("address") or "United Kingdom")
    q=f'"{company_name}" {loc} site:facebook.com'
    url="https://html.duckduckgo.com/html/?q="+parse.quote(q)
    if job_id:_job_set(job_id,detail=f"No website found — checking Facebook • {company or company_name}",company=company or company_name,current_url="")
    try:
        def do_search():
            req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; YMSProspectFinder/4.2.2; +business-research)","Accept":"text/html"})
            with request.urlopen(req,timeout=10) as r:return r.read(320000).decode("utf-8","ignore")
        raw=_transient_call("Facebook search",do_search,job_id,company or company_name,attempts=3)
    except Exception as ex:
        return {"found":False,"reason":"Facebook lookup unavailable: "+str(ex)[:140]}
    rows=[]
    for href,title_html in re.findall(r'(?is)<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw):
        fb=_facebook_candidate_url(href)
        if not fb:continue
        title=html_text(title_html)
        score=SequenceMatcher(None,norm_name(company_name),norm_name(title)).ratio()
        path_words=set(re.findall(r"[a-z0-9]+",urlparse(fb).path.lower()))
        name_words=set(re.findall(r"[a-z0-9]+",norm_name(company_name)))
        if name_words and path_words:score+=min(.22,.055*len(name_words & path_words))
        loc_token=(postcode(str(loc)) or str(loc).split(",",1)[0]).lower()
        if loc_token and loc_token in title.lower():score+=.08
        rows.append((score,fb,title))
    if not rows:
        return {"found":False,"reason":"No likely Facebook business page found"}
    rows.sort(reverse=True,key=lambda x:x[0]);score,fb,title=rows[0]
    if score<.48:return {"found":False,"reason":"Facebook results were too ambiguous"}
    return {"found":True,"url":fb,"title":title,"match_score":round(min(score,1)*100)}


def facebook_public_evidence(l, progress=None):
    fb=l.get("facebook_url") or (l.get("website") if _is_facebook_url(l.get("website")) else "")
    if not fb:return {"text":"","pages":[],"attempted_pages":[],"evidence_pages":[],"fetched_at":nowiso(),"source":"Facebook"}
    title=l.get("facebook_title") or l.get("company") or ""
    snippets=[]
    raw=""
    if progress:progress(0,1,"Checking public Facebook page",fb,0)
    try:
        raw,final=fetch_html(fb,timeout=10,max_bytes=260000)
        fb=final or fb
        for pat in (
            r'(?is)<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
            r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)'):
            m=re.search(pat,raw)
            if m:snippets.append(unescape(m.group(1)))
        txt=html_text(raw)
        if txt and len(txt)>80:snippets.append(txt[:6500])
    except Exception:
        pass
    base=[title,l.get("company",""),l.get("address",""),l.get("sector","")]+snippets
    text=re.sub(r"\s+"," "," ".join(str(x) for x in base if x)).strip()
    # Facebook often returns a login shell. Do not pretend generic Facebook text is business evidence.
    generic=("log into facebook" in text.lower() or "facebook helps you connect" in text.lower())
    if generic and len(snippets)<=1:text=" ".join(str(x) for x in base[:4] if x).strip()
    if progress:progress(1,1,"Facebook checked",fb,1 if len(text)>120 else 0)
    return {"text":text[:12000],"pages":[fb] if text else [],"attempted_pages":[fb],"evidence_pages":[fb] if text else [],"fetched_at":nowiso(),"source":"Facebook public page","facebook_url":fb}


def resolve_web_presence(id_, l, job_id="", company=""):
    """Resolve normal website first, then a Facebook business page fallback."""
    if not l:return l
    company=company or l.get("company") or "Prospect"
    # If Places gave Facebook as the website, classify it correctly as a social fallback.
    if _is_facebook_url(l.get("website")):
        fb=l.get("website")
        def move_fb(x):x["facebook_url"]=fb;x["facebook_checked_at"]=nowiso();x["website"]="";return dict(x)
        l=update_lead(id_,move_fb) or l
    if not l.get("website") and not l.get("place_id"):
        try:
            if job_id:_job_set(job_id,detail=f"Finding company on Google • {company}",company=company,current_url="")
            r=_transient_call("Google lookup",lambda:resolve_google_for_ch(l),job_id,company,attempts=3)
            if r.get("matched"):
                l=update_lead(id_,lambda x:(merge_into(x,r["lead"]) or dict(x))) or get_lead(id_) or l
        except Exception:pass
    if not l.get("website") and l.get("place_id"):
        key=cfg().get("google_places_key")
        if key:
            try:
                if job_id:_job_set(job_id,detail=f"Finding company website • {company}",company=company,current_url="")
                p2=_transient_call("Google Places",lambda:google_details(l["place_id"],key,"enterprise"),job_id,company,attempts=3)
                def apply_google_presence(x):merge_into(x,gp_to_lead(p2,x.get("sector",""),"Google enterprise enrichment"));return dict(x)
                l=update_lead(id_,apply_google_presence) or get_lead(id_) or l
            except Exception:pass
    if _is_facebook_url(l.get("website")):
        fb=l.get("website")
        def move_fb2(x):x["facebook_url"]=fb;x["facebook_checked_at"]=nowiso();x["website"]="";return dict(x)
        l=update_lead(id_,move_fb2) or get_lead(id_) or l
    if not l.get("website") and not l.get("facebook_url"):
        fb=find_facebook_fallback(l,job_id,company)
        def save_fb(x):
            x["facebook_checked_at"]=nowiso()
            if fb.get("found"):
                x["facebook_url"]=fb.get("url","");x["facebook_title"]=fb.get("title","");x["facebook_match_score"]=fb.get("match_score",0);x.pop("web_skip_reason",None)
            else:x["facebook_lookup_reason"]=fb.get("reason","")
            return dict(x)
        l=update_lead(id_,save_fb) or get_lead(id_) or l
    return l


def collect_presence_evidence(id_, l, progress=None, job_id="", company=""):
    if l.get("website"):
        def crawl():return web_enrich(l,progress)
        ev=_transient_call("website",crawl,job_id,company or l.get("company",""),attempts=3)
        return ev
    if l.get("facebook_url"):
        return facebook_public_evidence(l,progress)
    return {"text":"","pages":[],"attempted_pages":[],"evidence_pages":[],"fetched_at":nowiso(),"source":"none"}
'''


NEW_AI_RETRY = r'''def _ai_with_retry(job_id, lead, base_pct, span, company):
    # V4.2.2: absorb short OpenAI/API wobbles automatically instead of immediately
    # dumping the user out of a long qualification run.
    delays=(2,5,10,20,40)
    max_attempts=6
    for attempt in range(1,max_attempts+1):
        try:
            return ai_analyse(lead)
        except Exception as ex:
            kind=_service_failure_kind("ai",ex)
            if kind in ("quota","auth","error") or attempt>=max_attempts:
                raise
            delay=delays[min(attempt-1,len(delays)-1)]
            _job_set(job_id,detail=f"Temporary OpenAI issue — retry {attempt}/{max_attempts-1} in {delay}s • {company}",failure_kind=kind,percent=round(base_pct+span*.34,1),company=company)
            time.sleep(delay)


'''


NEW_PIPELINE = r'''def _process_pipeline_lead(id_, job_id="", company_index=0, total=0):
    """Shared resilient one-company Smart Pipeline used by manual batches and Smart Finder."""
    l=get_lead(id_);company=(l or {}).get("company") or "Prospect"
    if not l:raise SkipProspect("Prospect record was not found")
    done,why=_action_complete(l,"pipeline")
    if done:return {"status":"already","reason":why,"company":company}
    if hard_noise_reason(l) or l.get("discovery_excluded"):
        raise SkipProspect(l.get("discovery_exclusion_reason") or "Obvious non-industrial / irrelevant result")
    if not l.get("ai"):
        l=resolve_web_presence(id_,l,job_id,company) or get_lead(id_) or l
        if not l.get("website") and not l.get("facebook_url"):
            reason="No company website or Facebook business page found"
            update_lead(id_,lambda x:(x.update({"web_skip_reason":reason,"ai_skip_reason":reason}) or True))
            raise SkipProspect(reason)
        ev=l.get("web_evidence") or {}
        if not ev.get("text"):
            def pipe_progress(page_index,page_total,message,current_url,pages_found):
                if job_id:_job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company)
            current=l.get("website") or l.get("facebook_url") or ""
            if job_id:_job_set(job_id,detail=f"Reading public business evidence • {company}",company=company,current_url=current)
            def pipe_enrich(x):
                ev2=collect_presence_evidence(id_,x,pipe_progress,job_id,company);x["web_evidence"]=ev2;x["emails"]=merge_lists(x.get("emails",[]),ev2.get("emails",[]))
                if ev2.get("contact_page"):x["contact_page"]=ev2["contact_page"]
                if ev2.get("linkedin_url"):x["linkedin_url"]=ev2["linkedin_url"]
                x.pop("web_skip_reason",None);return ev2
            ev=update_lead(id_,pipe_enrich) or {}
            if len((ev.get("text") or "").strip())<120:
                reason=("Facebook page found, but not enough public evidence could be read" if l.get("facebook_url") and not l.get("website") else "No usable website evidence")
                update_lead(id_,lambda x:(x.update({"web_skip_reason":reason,"ai_skip_reason":reason}) or True))
                raise SkipProspect(reason)
        gate=apply_website_relevance_gate(id_)
        if not gate.get("pass"):
            update_lead(id_,lambda x:(x.update({"ai_skip_reason":"Filtered before AI — "+str(gate.get("reason") or "not relevant")}) or True))
            raise SkipProspect("Filtered before AI — "+str(gate.get("reason") or "not relevant"))
        l=get_lead(id_) or l
        current=l.get("website") or l.get("facebook_url") or ""
        if job_id:_job_set(job_id,detail=f"AI qualifying • {company}",company=company,current_url=current)
        result=_ai_with_retry(job_id,l,0,0,company)
        if job_id:_job_set(job_id,detail=f"Saving priority + email draft • {company}",company=company)
        def pipe_save_ai(x):x["ai"]=result;x.pop("ai_skip_reason",None);return result
        update_lead(id_,pipe_save_ai)
    current=get_lead(id_) or {}
    if cfg().get("auto_capsule_high_priority",False) and cfg().get("capsule_token") and current.get("outreach_priority_code") in ("P1","P2") and not (current.get("capsule") or {}).get("capsule_id"):
        if job_id:_job_set(job_id,detail=f"Sending high-priority prospect to Capsule • {company}",company=company,current_url="")
        update_lead(id_,lambda x:(x.update({"capsule":capsule_sync(x)}) or x["capsule"]))
    return {"status":"done","company":company}


'''

NEW_WEB_ONE = r'''        if action=="web_one":
            if hard_noise_reason(l) or l.get("discovery_excluded"):
                raise SkipProspect(l.get("discovery_exclusion_reason") or "Obvious non-industrial / irrelevant result")
            def update_cb_one(page_index,page_total,message,current_url,pages_found):
                _job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company,company_index=min(selected_total,already_done+work_pos+1))
            l=resolve_web_presence(id_,l,job_id,company) or get_lead(id_) or l
            if not l.get("website") and not l.get("facebook_url"):
                reason="No company website or Facebook business page found"
                update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True))
                raise SkipProspect(reason)
            current=l.get("website") or l.get("facebook_url") or ""
            _job_set(job_id,detail=f"Reading public business evidence • {company}",company=company,current_url=current)
            def enrich_one_manual(x):
                ev=collect_presence_evidence(id_,x,update_cb_one,job_id,company);x["web_evidence"]=ev;x["emails"]=merge_lists(x.get("emails",[]),ev.get("emails",[]))
                if ev.get("contact_page"):x["contact_page"]=ev["contact_page"]
                if ev.get("linkedin_url"):x["linkedin_url"]=ev["linkedin_url"]
                x.pop("web_skip_reason",None);return ev
            ev=update_lead(id_,enrich_one_manual) or {}
            if len((ev.get("text") or "").strip())<120:
                reason=("Facebook page found, but not enough public evidence could be read" if l.get("facebook_url") and not l.get("website") else "Website found, but no usable business pages could be read")
                update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True))
                raise SkipProspect(reason)
            return {"status":"done","id":id_,"company":company,"pos":work_pos}

'''

NEW_WEB_BULK = r'''        if action=="web":
            def update_cb(page_index,page_total,message,current_url,pages_found):
                _job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company,company_index=min(selected_total,already_done+work_pos+1))
            l=resolve_web_presence(id_,l,job_id,company) or get_lead(id_) or l
            if not l.get("website") and not l.get("facebook_url"):raise SkipProspect("No company website or Facebook business page found")
            def enrich_one(x):
                ev=collect_presence_evidence(id_,x,update_cb,job_id,company);x["web_evidence"]=ev;x["emails"]=merge_lists(x.get("emails",[]),ev.get("emails",[]))
                if ev.get("contact_page"):x["contact_page"]=ev["contact_page"]
                if ev.get("linkedin_url"):x["linkedin_url"]=ev["linkedin_url"]
                x.pop("web_skip_reason",None);return ev
            ev=update_lead(id_,enrich_one) or {}
            if len((ev.get("text") or "").strip())<120:
                reason=("Facebook page found, but not enough public evidence could be read" if l.get("facebook_url") and not l.get("website") else "No usable website pages found")
                update_lead(id_,lambda x:(x.update({"web_skip_reason":reason}) or True));raise SkipProspect(reason)
            return {"status":"done","id":id_,"company":company,"pos":work_pos}

'''

NEW_AI_ONE = r'''        if action=="ai_one":
            if hard_noise_reason(l) or l.get("discovery_excluded"):
                raise SkipProspect(l.get("discovery_exclusion_reason") or "Obvious non-industrial / irrelevant result")
            l=resolve_web_presence(id_,l,job_id,company) or get_lead(id_) or l
            if not l.get("website") and not l.get("facebook_url"):
                reason="No company website or Facebook business page found — AI not run"
                update_lead(id_,lambda x:(x.update({"web_skip_reason":"No web presence found","ai_skip_reason":reason}) or True));raise SkipProspect(reason)
            ev=l.get("web_evidence") or {}
            if not ev.get("text"):
                def ai_one_progress(page_index,page_total,message,current_url,pages_found):
                    _job_set(job_id,detail=f"{message} • {company}",current_url=current_url,page_index=page_index,page_total=page_total,pages_found=pages_found,company=company,company_index=min(selected_total,already_done+work_pos+1))
                current=l.get("website") or l.get("facebook_url") or ""
                _job_set(job_id,detail=f"Reading public business evidence • {company}",company=company,current_url=current)
                def ai_one_enrich(x):
                    ev2=collect_presence_evidence(id_,x,ai_one_progress,job_id,company);x["web_evidence"]=ev2;x["emails"]=merge_lists(x.get("emails",[]),ev2.get("emails",[]))
                    if ev2.get("contact_page"):x["contact_page"]=ev2["contact_page"]
                    if ev2.get("linkedin_url"):x["linkedin_url"]=ev2["linkedin_url"]
                    x.pop("web_skip_reason",None);return ev2
                ev=update_lead(id_,ai_one_enrich) or {}
                if len((ev.get("text") or "").strip())<120:
                    reason=("Facebook page found, but not enough public evidence could be read — AI not run" if l.get("facebook_url") and not l.get("website") else "No usable website evidence — AI not run")
                    update_lead(id_,lambda x:(x.update({"web_skip_reason":reason.replace(" — AI not run",""),"ai_skip_reason":reason}) or True));raise SkipProspect(reason)
            gate_fn=globals().get("apply_website_relevance_gate")
            if callable(gate_fn):
                gate=gate_fn(id_)
                if not gate.get("pass"):
                    reason="Filtered before AI — "+str(gate.get("reason") or "not relevant");update_lead(id_,lambda x:(x.update({"ai_skip_reason":reason}) or True));raise SkipProspect(reason)
            l=get_lead(id_) or l;current=l.get("website") or l.get("facebook_url") or ""
            _job_set(job_id,detail=f"AI qualifying • {company}",company=company,current_url=current,company_index=min(selected_total,already_done+work_pos+1))
            result=_ai_with_retry(job_id,l,0,0,company)
            _job_set(job_id,detail=f"Saving YMS score, priority + email draft • {company}",company=company,current_url="")
            def save_ai_one(x):x["ai"]=result;x.pop("ai_skip_reason",None);x.pop("web_skip_reason",None);return result
            update_lead(id_,save_ai_one)
            current=get_lead(id_) or {}
            if cfg().get("auto_capsule_high_priority",False) and cfg().get("capsule_token") and current.get("outreach_priority_code") in ("P1","P2") and not (current.get("capsule") or {}).get("capsule_id"):
                _job_set(job_id,detail=f"Sending high-priority prospect to Capsule • {company}",company=company,current_url="")
                update_lead(id_,lambda x:(x.update({"capsule":capsule_sync(x)}) or x["capsule"]))
            return {"status":"done","id":id_,"company":company,"pos":work_pos}

'''

NEW_RESUME = r'''def resume_progress_job(job_id):
    with JOB_LOCK:
        job=JOBS.get(job_id)
        if not job:raise RuntimeError("Saved background job was not found.")
        if job.get("status")=="running":return dict(job)
        if not job.get("resumable") and job.get("status") not in ("paused","failed"):raise RuntimeError("This job has already finished and does not need resuming.")
        action=job.get("action","")
        ids=list(job.get("ids") or [])
        # Smart Finder owns its own persistent pending_ids/query cursor, so an empty
        # normal ids queue is expected and must not block resume.
        if action!="finder" and not ids:raise RuntimeError("The saved job does not contain a remaining queue.")
        job["status"]="queued";job["detail"]=("Smart Finder resume queued — rechecking saved checkpoints" if action=="finder" else "Resume queued — rechecking saved checkpoints");job["error"]="";job["resumable"]=False;job["failure_kind"]="";job["stop_requested"]=False;job["finished_at"]=0;job["updated_at"]=time.time();_persist_jobs_locked()
    if action=="finder":threading.Thread(target=_run_smart_finder,args=(job_id,),daemon=True).start()
    else:threading.Thread(target=_run_progress_job,args=(job_id,action,ids),daemon=True).start()
    return _job_get(job_id)


'''

NEW_START_FINDER = r'''def start_smart_finder(query_limit=100,pages=1):
    c=cfg()
    if c.get("free_mode",True):raise RuntimeError("Smart Finder needs Full Mode because it automatically AI-qualifies relevant companies. Switch Full Mode on in Settings first.")
    if not c.get("google_places_key"):raise RuntimeError("Google Places is not configured.")
    if not c.get("openai_key"):raise RuntimeError("OpenAI is not configured.")
    latest=_finder_job_latest()
    if latest and latest.get("status") in ("queued","running"):return latest
    # V4.2.2: Start doubles as Resume. No activity-panel dead end.
    if latest and latest.get("status")=="paused" and latest.get("resumable"):
        return resume_progress_job(latest.get("id"))
    limit=max(1,min(int(query_limit or 100),1000));pages=max(1,min(int(pages or 1),3));job_id=uuid.uuid4().hex
    with JOB_LOCK:
        JOBS[job_id]={"id":job_id,"action":"finder","ids":[],"status":"queued","percent":0,"detail":"Smart Finder queued","query_limit":limit,"queries_done":0,"pages":pages,"workers":3,"google_hits":0,"noise_blocked":0,"new_candidates":0,"qualified":0,"filtered":0,"skipped":0,"waiting":0,"active_workers":0,"pending_ids":[],"processed_ids":[],"stop_requested":False,"completed":0,"total":limit,"remaining":limit,"created_at":time.time(),"updated_at":time.time(),"error":"","failure_kind":"","resumable":False,"awake_protected":False,"checkpointed":True}
        _persist_jobs_locked()
    threading.Thread(target=_run_smart_finder,args=(job_id,),daemon=True).start()
    return _job_get(job_id)


'''

NEW_STOP_FINDER = r'''def stop_smart_finder():
    j=_finder_job_latest()
    if not j or j.get("status") not in ("queued","running"):
        return {"ok":True,"message":"Smart Finder is not currently running.",**(j or smart_finder_status())}
    _job_set(j["id"],stop_requested=True,detail="Pausing Smart Finder safely • finishing current company work")
    return {"ok":True,"message":"Pause requested. Current company work will save, then you can Resume Smart Finder whenever you want.",**(_job_get(j["id"]) or {})}
'''


def patch_backend(source):
    source,n=re.subn(r'APP_VERSION\s*=\s*["\'][^"\']+["\']',f'APP_VERSION = "{TARGET_VERSION}"',source,count=1)
    if n!=1:raise RuntimeError("Could not update APP_VERSION")

    # Broaden transient network/service classification.
    source=source.replace('"http 500","http 502","http 503","http 504"','"http 408","http 500","http 502","http 503","http 504","http 520","http 521","http 522","http 523","http 524","service unavailable","bad gateway","gateway timeout"',1)

    # Replace AI retry function wholesale.
    a=source.find('def _ai_with_retry(job_id, lead, base_pct, span, company):\n')
    b=source.find('PRODUCT_RULES = {',a)
    if a<0 or b<0:raise RuntimeError("Could not locate AI retry function")
    source=source[:a]+NEW_AI_RETRY+source[b:]

    # Insert fallback helpers immediately before web_enrich.
    if 'def find_facebook_fallback(' not in source:
        marker='def web_enrich(l, progress=None):\n'
        source=replace_once(source,marker,PRESENCE_HELPERS+'\n\n'+marker,'web-enrichment insertion point')

    # Replace shared pipeline function.
    a=source.find('def _process_pipeline_lead(id_, job_id="", company_index=0, total=0):\n')
    b=source.find('def _run_smart_finder(job_id):\n',a)
    if a<0 or b<0:raise RuntimeError("Could not locate Smart Finder pipeline function")
    source=source[:a]+NEW_PIPELINE+source[b:]

    # Make user Stop a real resumable pause rather than a dead-end complete job.
    old_stop_completion='''        else:\n            stopped=stop_requested\n            detail=(f"Stopped safely • {queries_done} searches • {qualified} qualified • {filtered} filtered before AI • {len(pending)} discovered prospects left for later" if stopped else f"Complete • {queries_done} searches • {qualified} qualified • {filtered} filtered before AI • {noise_blocked} obvious noise blocked")\n            _job_set(job_id,status="complete",percent=100,resumable=False,detail=detail,finished_at=time.time(),queries_done=queries_done,query_limit=query_limit,google_hits=google_hits,noise_blocked=noise_blocked,new_candidates=new_candidates,qualified=qualified,filtered=filtered,skipped=skipped,waiting=len(pending),active_workers=0,pending_ids=list(pending),processed_ids=list(processed),completed=query_limit if not stopped else queries_done,total=query_limit,remaining=0 if not stopped else max(0,query_limit-queries_done),awake_protected=False,stopped=stopped)\n'''
    new_stop_completion='''        else:\n            stopped=stop_requested\n            if stopped:\n                detail=f"Paused by you • {queries_done}/{query_limit} searches • {qualified} qualified • {filtered} filtered • {len(pending)} waiting — Resume Smart Finder when ready"\n                _job_set(job_id,status="paused",resumable=True,percent=min(99,float((_job_get(job_id) or {}).get("percent",0) or 0)),detail=detail,finished_at=time.time(),queries_done=queries_done,query_limit=query_limit,google_hits=google_hits,noise_blocked=noise_blocked,new_candidates=new_candidates,qualified=qualified,filtered=filtered,skipped=skipped,waiting=len(pending),active_workers=0,pending_ids=list(pending),processed_ids=list(processed),completed=queries_done,total=query_limit,remaining=max(0,query_limit-queries_done),awake_protected=False,stopped=True,stop_requested=False)\n            else:\n                detail=f"Complete • {queries_done} searches • {qualified} qualified • {filtered} filtered before AI • {noise_blocked} obvious noise blocked"\n                _job_set(job_id,status="complete",percent=100,resumable=False,detail=detail,finished_at=time.time(),queries_done=queries_done,query_limit=query_limit,google_hits=google_hits,noise_blocked=noise_blocked,new_candidates=new_candidates,qualified=qualified,filtered=filtered,skipped=skipped,waiting=len(pending),active_workers=0,pending_ids=list(pending),processed_ids=list(processed),completed=query_limit,total=query_limit,remaining=0,awake_protected=False,stopped=False,stop_requested=False)\n'''
    source=replace_once(source,old_stop_completion,new_stop_completion,'Smart Finder stop completion block')

    # Fix the core resume bug: Finder has no normal ids queue.
    a=source.find('def resume_progress_job(job_id):\n')
    b=source.find('# ---------------------------------------------------------------------------\n# Over-the-air updater',a)
    if a<0 or b<0:raise RuntimeError("Could not locate background-job resume function")
    source=source[:a]+NEW_RESUME+source[b:]

    # Start automatically resumes the latest paused Finder.
    a=source.find('def start_smart_finder(query_limit=100,pages=1):\n')
    b=source.find('def stop_smart_finder():\n',a)
    if a<0 or b<0:raise RuntimeError("Could not locate Smart Finder start function")
    source=source[:a]+NEW_START_FINDER+source[b:]
    a=source.find('def stop_smart_finder():\n')
    # end at next raw-string terminator is impossible in final app; use action-complete or next helper after function.
    b=source.find('\n\ndef _action_complete',a)
    if b<0:
        # In V4.2 final app stop_smart_finder is immediately followed by _action_complete later in file.
        b=source.find('\n\ndef ',a+30)
    if a<0 or b<0:raise RuntimeError("Could not locate Smart Finder stop function end")
    source=source[:a]+NEW_STOP_FINDER+source[b:]

    # Individual + bulk workers use the same resilient presence resolver.
    a=source.find('        if action=="web_one":\n')
    b=source.find('        if action=="web":\n',a)
    if a<0 or b<0:raise RuntimeError("Could not locate individual Website evidence worker")
    source=source[:a]+NEW_WEB_ONE+source[b:]
    a=source.find('        if action=="web":\n')
    b=source.find('        if action=="pipeline":\n',a)
    if a<0 or b<0:raise RuntimeError("Could not locate bulk Website evidence worker")
    source=source[:a]+NEW_WEB_BULK+source[b:]
    a=source.find('        if action=="ai_one":\n')
    b=source.find('        if action=="ai":\n',a)
    if a<0 or b<0:raise RuntimeError("Could not locate individual AI worker")
    source=source[:a]+NEW_AI_ONE+source[b:]

    # Bulk AI can use Facebook evidence too.
    source=source.replace('            if not l.get("website"):\n                update_lead(id_,lambda x:(x.update({"ai_skip_reason":"No website"}) or True));raise SkipProspect("No website")\n', '            if not l.get("website") and not l.get("facebook_url"):\n                update_lead(id_,lambda x:(x.update({"ai_skip_reason":"No web presence found"}) or True));raise SkipProspect("No web presence found")\n',1)
    source=source.replace('current_url=l.get("website","")','current_url=(l.get("website") or l.get("facebook_url") or "")')

    # Old no-website skip markers must be retried now that Facebook fallback exists.
    source=source.replace('if "no website" in reason and not l.get("website"):return True,"Previously confirmed: no website"','if "no web presence found" in reason and not l.get("website") and not l.get("facebook_url") and l.get("facebook_checked_at"):return True,"Previously confirmed: no web presence"',1)
    old_web_complete='''    if action=="web":\n        ev=l.get("web_evidence") or {}\n        if ev.get("fetched_at") and (ev.get("text") or ev.get("attempted_pages")):return True,"Website evidence already crawled"\n        reason=(l.get("web_skip_reason") or "").lower()\n        if reason and (not l.get("website") or "no usable website" in reason or "no company website" in reason):return True,"Previous website crawl already resolved"\n        return False,""\n'''
    new_web_complete='''    if action=="web":\n        ev=l.get("web_evidence") or {}\n        if ev.get("fetched_at") and (ev.get("text") or ev.get("attempted_pages")):return True,"Public business evidence already checked"\n        reason=(l.get("web_skip_reason") or "").lower()\n        if "no web presence found" in reason and l.get("facebook_checked_at") and not l.get("website") and not l.get("facebook_url"):return True,"Previously confirmed: no web presence"\n        if ("no usable website" in reason or "not enough public evidence" in reason) and (l.get("website") or l.get("facebook_url")):return True,"Previous public evidence check already resolved"\n        return False,""\n'''
    if old_web_complete in source:source=source.replace(old_web_complete,new_web_complete,1)

    # Add explicit Finder resume endpoint.
    source=source.replace('            if p=="/api/finder/stop":\n                self.sendj(stop_smart_finder());return\n', '            if p=="/api/finder/stop":\n                self.sendj(stop_smart_finder());return\n            if p=="/api/finder/resume":\n                j=_finder_job_latest()\n                if not j:raise RuntimeError("No saved Smart Finder session was found.")\n                self.sendj(resume_progress_job(j.get("id","")));return\n',1)
    return source


RESUME_JS = r'''
async function resumeSavedJob(id,title="Resuming saved work"){
 try{
  showProgress(title);let j=await api("/api/job/resume",{id});paintJob(j);
  if(j.action==="finder"){paintFinderStatus(j);pollFinderJob(j.id);return j}
  while(true){await new Promise(r=>setTimeout(r,600));let rr=await fetch(`/api/job/status?id=${encodeURIComponent(j.id)}`,{cache:"no-store"}),s=await rr.json();if(!rr.ok||s.error)throw Error(s.error||"Resume status failed");paintJob(s);if(s.status==="complete"){let d=$("progressDone");d.className="progressDone ok";d.textContent="Resumed work completed successfully.";await loadLeads();setTimeout(hideProgress,900);return s}if(s.status==="paused"){let d=$("progressDone");d.className="progressDone warn";d.innerHTML=`${esc(s.detail||"Paused safely")}<div style="margin-top:8px"><button class="btn sm" onclick="resumeSavedJob('${s.id}','Resume remaining')">Resume remaining</button></div>`;await loadLeads();return s}}
 }catch(e){toast(e.message,"bad",7000)}
}
async function resumeSmartFinder(){try{let j=await api("/api/finder/resume",{});paintFinderStatus(j);showProgress("Smart Finder • resumed");paintJob(j);pollFinderJob(j.id)}catch(e){toast(e.message,"bad",7000)}}
'''


def patch_frontend(html):
    platform="Mac" if sys.platform=="darwin" else ("Windows" if os.name=="nt" else "Desktop")
    html=re.sub(r'<title>YMS Prospect Finder V[^<]+ — YMS-Tools</title>',f'<title>YMS Prospect Finder V{TARGET_VERSION} {platform} — YMS-Tools</title>',html,count=1)
    html=re.sub(r'<b id="versionLabel">Prospect Finder V[^<]+</b>',f'<b id="versionLabel">Prospect Finder V{TARGET_VERSION} {platform}</b>',html,count=1)

    # Facebook link in Contact card.
    contact='''${l.website?`<a target="_blank" href="${esc(l.website)}">Website ↗</a> · `:''}${l.contact_page?`<a target="_blank" href="${esc(l.contact_page)}">Contact page ↗</a> · `:''}${l.linkedin_url?`<a target="_blank" href="${esc(l.linkedin_url)}">LinkedIn ↗</a>`:''}'''
    replacement='''${l.website?`<a target="_blank" href="${esc(l.website)}">Website ↗</a> · `:''}${l.facebook_url?`<a target="_blank" href="${esc(l.facebook_url)}">Facebook ↗</a> · `:''}${l.contact_page?`<a target="_blank" href="${esc(l.contact_page)}">Contact page ↗</a> · `:''}${l.linkedin_url?`<a target="_blank" href="${esc(l.linkedin_url)}">LinkedIn ↗</a>`:''}'''
    if contact in html:html=html.replace(contact,replacement,1)

    # Make the individual-work copy explain the fallback.
    html=html.replace('Missing website/evidence is found automatically. Results refresh here when finished.','Missing website/evidence is found automatically — including a Facebook business-page fallback. Results refresh here when finished.',1)

    # Explicit Finder Resume buttons. Start button also still works as resume.
    dash_stop='<button class="btn" id="finderDashStop" onclick="stopSmartFinder()" disabled>Stop safely</button>'
    if dash_stop in html and 'id="finderDashResume"' not in html:
        html=html.replace(dash_stop,dash_stop+'<button class="btn green" id="finderDashResume" onclick="resumeSmartFinder()" style="display:none">Resume Smart Finder</button>',1)
    ctrl_stop='<button class="btn" id="finderStopBtn" onclick="stopSmartFinder()" disabled>Stop safely</button>'
    if ctrl_stop in html and 'id="finderResumeBtn"' not in html:
        html=html.replace(ctrl_stop,ctrl_stop+'<button class="btn green" id="finderResumeBtn" onclick="resumeSmartFinder()" style="display:none">Resume Finder</button>',1)

    # Add helper before existing finder stop function or before show().
    if 'async function resumeSavedJob(' not in html:
        marker='async function stopSmartFinder()'
        if marker in html:html=html.replace(marker,RESUME_JS+'\n'+marker,1)
        else:
            marker='function show(id,b)'
            html=replace_once(html,marker,RESUME_JS+'\n'+marker,'frontend JS insertion point')

    # Finder status always exposes Resume when paused.
    old='["finderDashStop","finderStopBtn"].forEach(id=>{if($(id))$(id).disabled=!running});'
    new=old+'["finderDashResume","finderResumeBtn"].forEach(id=>{if($(id))$(id).style.display=paused?"inline-flex":"none"});'
    if old in html and 'finderDashResume","finderResumeBtn' not in html:html=html.replace(old,new,1)

    # A stopped/paused Finder must be described as resumable.
    html=html.replace('Stopped safely — completed work has been saved.','Paused safely — completed work has been saved. Click Resume Smart Finder when you are ready.',1)

    # runProgressJob previously ignored paused state entirely. Add visible resume handling.
    old='if(j.status==="failed"){let d=$("progressDone");d.className="progressDone bad";d.textContent="Failed: "+(j.error||"Unknown error");setTimeout(hideProgress,2200);throw Error(j.error||"Job failed")}'
    new='if(j.status==="paused"){let d=$("progressDone");d.className="progressDone warn";d.innerHTML=`${esc(j.detail||"Paused safely — completed work is saved.")}<div style="margin-top:8px"><button class="btn sm" onclick="resumeSavedJob(\'${j.id}\',\'Resume remaining\')">Resume remaining</button></div>`;await loadLeads();return j}'+old
    if old in html:html=html.replace(old,new,1)

    # Individual step shouldn't report success when its job paused.
    old2='let l=leads.find(x=>x.id===id),reason=action==="web_one"?(l?.web_skip_reason||""):(l?.ai_skip_reason||l?.web_skip_reason||"");\n  if(Number(j.skipped)||reason)'
    new2='let l=leads.find(x=>x.id===id),reason=action==="web_one"?(l?.web_skip_reason||""):(l?.ai_skip_reason||l?.web_skip_reason||"");\n  if(j?.status==="paused"){toast(j.detail||"Paused safely — use Resume remaining to continue.","warn",8000);return j}\n  if(Number(j.skipped)||reason)'
    if old2 in html:html=html.replace(old2,new2,1)

    # AI confirmation copy mentions Facebook fallback.
    html=html.replace('Prospect Finder will automatically find its website, read useful evidence, check relevance, then run AI and create the score, priority and personalised email draft.','Prospect Finder will automatically find its website or Facebook business page, read useful public evidence, check relevance, then run AI and create the score, priority and personalised email draft.',1)
    return html


# Locate the exact safe backup created by the OTA updater.
backups=DATA_DIR/"update-backups";choices=[]
if backups.exists():
    for p in backups.glob("before-"+TARGET_VERSION+"-*"):
        if (p/"server.py").exists() and (p/"index.html").exists():
            try:choices.append((p.stat().st_mtime,p))
            except Exception:pass
if not choices:fail("V4.2.2 could not find the safe pre-update backup. Nothing in your prospect database was changed.")
backup=max(choices,key=lambda x:x[0])[1]

try:
    old_server=(backup/"server.py").read_text("utf-8")
    old_html=(backup/"index.html").read_text("utf-8")
    if 'def start_smart_finder(' not in old_server or 'action=="ai_one"' not in old_server:
        raise RuntimeError("V4.2.2 requires the V4.2.1 Smart Finder build first")
    new_server=patch_backend(old_server)
    new_html=patch_frontend(old_html)
    compile(new_server,"server.py","exec")
    required=(
        'APP_VERSION = "4.2.2"','def find_facebook_fallback(','def resolve_web_presence(','def resume_progress_job(','action=="ai_one"','def start_smart_finder('
    )
    missing=[x for x in required if x not in new_server]
    if missing:raise RuntimeError("V4.2.2 backend validation failed: "+", ".join(missing))
    if 'resumeSmartFinder' not in new_html or 'Facebook ↗' not in new_html:
        raise RuntimeError("V4.2.2 interface validation failed")
    ts=APP_DIR/"server.py.ota-new";th=APP_DIR/"index.html.ota-new"
    ts.write_text(new_server,encoding="utf-8");th.write_text(new_html,encoding="utf-8")
    os.replace(ts,APP_DIR/"server.py");os.replace(th,APP_DIR/"index.html")
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    (DATA_DIR/"last_ota_update.txt").write_text(f"{TARGET_VERSION}\n{time.strftime('%Y-%m-%d %H:%M:%S')}\nStability pass: 503 retries + Facebook fallback + Smart Finder resume fixed\n",encoding="utf-8")
except Exception as exc:
    fail(exc)

os.execv(sys.executable,[sys.executable,str(APP_DIR/"server.py")])
