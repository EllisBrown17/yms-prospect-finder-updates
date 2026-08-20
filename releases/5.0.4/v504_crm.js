// V5.0.4 CRM + smart follow-up layer
(function(){
  'use strict';
  const V504_KEY='yms_v504_crm_notifications';
  const V504_NOTIFIED='yms_v504_crm_notified';
  let v504Rows=[];
  let v504Filter='due';
  let v504RefreshTimer=null;

  function esc(v){
    try{return typeof v5e==='function'?v5e(String(v??'')):String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}catch(_){return String(v??'')}
  }
  function isoLocal(d){
    const y=d.getFullYear(),m=String(d.getMonth()+1).padStart(2,'0'),day=String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${day}`;
  }
  function today(){return isoLocal(new Date())}
  function addBusinessDays(startIso,n){
    let d=startIso?new Date(startIso+'T12:00:00'):new Date();
    let added=0;
    while(added<n){d.setDate(d.getDate()+1);let wd=d.getDay();if(wd!==0&&wd!==6)added++}
    return isoLocal(d);
  }
  function selectedId(){try{return typeof v5OutSelected!=='undefined'?v5OutSelected:''}catch(_){return ''}}
  function selectedRow(){let id=selectedId();return v504Rows.find(r=>r&&r.id===id)||null}
  function suggestedDays(row){let a=Number(row?.state?.attempts||0);return a<=0?3:(a===1?5:10)}
  function suggestFollowDate(row){return addBusinessDays(today(),suggestedDays(row))}
  function activeForReminder(row){
    let s=String(row?.state?.stage||'');
    return !['replied','closed','suppressed','qualified'].includes(s);
  }
  function hasBeenSent(row){return Number(row?.state?.attempts||0)>0}
  function dueKind(row){
    let f=String(row?.state?.next_followup||'');
    if(!f||!activeForReminder(row))return '';
    if(f<today())return 'overdue';
    if(f===today())return 'today';
    return 'waiting';
  }
  function stageLabel(s){
    try{return typeof v5StageLabel==='function'?v5StageLabel(s):String(s||'').replaceAll('_',' ')}catch(_){return String(s||'').replaceAll('_',' ')}
  }
  function statusText(row){
    let s=String(row?.state?.stage||''),kind=dueKind(row),f=String(row?.state?.next_followup||'');
    if(s==='replied')return 'Reply received';
    if(kind==='overdue')return `Overdue · ${f}`;
    if(kind==='today')return 'Follow up today';
    if(kind==='waiting')return `Follow up ${f}`;
    if(s==='qualified')return 'Qualified opportunity';
    if(s==='closed')return 'Closed';
    if(s==='suppressed')return 'Do not contact';
    return stageLabel(s||'sent_waiting');
  }
  function priority(row){
    let k=dueKind(row),s=String(row?.state?.stage||'');
    if(k==='overdue')return 0;if(k==='today')return 1;if(s==='replied')return 2;if(k==='waiting')return 3;return 4;
  }

  function ensureDashboard(){
    const page=document.getElementById('outreach');if(!page)return null;
    let root=document.getElementById('v504CrmDashboard');
    if(!root){
      root=document.createElement('section');root.id='v504CrmDashboard';root.className='v504Crm';
      let anchor=[...page.children].find(x=>x.classList&&x.classList.contains('v4SectionHead'));
      if(anchor)anchor.after(root);else page.prepend(root);
    }
    ensureNavBadge();
    return root;
  }
  function ensureNavBadge(){
    const els=[...document.querySelectorAll('button,a,[role="tab"]')];
    const nav=els.find(e=>{
      const txt=(e.textContent||'').trim().toLowerCase();
      const sig=((e.getAttribute('onclick')||'')+' '+(e.getAttribute('href')||'')+' '+(e.getAttribute('data-tab')||'')).toLowerCase();
      return txt.includes('outreach')&&sig.includes('outreach');
    });
    if(!nav)return;
    let badge=nav.querySelector('.v504NavBadge');
    if(!badge){badge=document.createElement('span');badge.className='v504NavBadge';nav.appendChild(badge)}
    const due=v504Rows.filter(r=>hasBeenSent(r)&&['overdue','today'].includes(dueKind(r))).length;
    badge.textContent=String(due);badge.style.display=due?'inline-flex':'none';
  }

  function filteredRows(){
    let rows=v504Rows.filter(hasBeenSent);
    if(v504Filter==='due')rows=rows.filter(r=>['overdue','today'].includes(dueKind(r)));
    else if(v504Filter==='overdue')rows=rows.filter(r=>dueKind(r)==='overdue');
    else if(v504Filter==='waiting')rows=rows.filter(r=>dueKind(r)==='waiting');
    else if(v504Filter==='replied')rows=rows.filter(r=>String(r?.state?.stage||'')==='replied');
    rows.sort((a,b)=>{
      let pa=priority(a),pb=priority(b);if(pa!==pb)return pa-pb;
      let da=String(a?.state?.next_followup||'9999'),db=String(b?.state?.next_followup||'9999');if(da!==db)return da.localeCompare(db);
      return String(a?.company||'').localeCompare(String(b?.company||''));
    });
    return rows;
  }

  function renderDashboard(){
    const root=ensureDashboard();if(!root)return;
    const sent=v504Rows.filter(hasBeenSent),over=sent.filter(r=>dueKind(r)==='overdue'),due=sent.filter(r=>dueKind(r)==='today'),waiting=sent.filter(r=>dueKind(r)==='waiting'),replied=sent.filter(r=>String(r?.state?.stage||'')==='replied');
    const rows=filteredRows();
    const notifSupported='Notification' in window;
    const notifOn=notifSupported&&localStorage.getItem(V504_KEY)==='1'&&Notification.permission==='granted';
    const filterButton=(key,label,count)=>`<button class="v504Stat ${v504Filter===key?'active':''}" onclick="v504SetCrmFilter('${key}')"><b>${count}</b><span>${label}</span></button>`;
    root.innerHTML=`
      <div class="v504Head">
        <div><div class="ey">YMS CRM</div><h2>Follow-up control</h2><p>Email a prospect, click <b>Email sent</b>, and YMS puts them into CRM automatically.</p></div>
        <button class="btn ${notifOn?'v504NotifOn':''}" onclick="v504EnableCrmNotifications()">${!notifSupported?'Desktop reminders unavailable':notifOn?'Desktop reminders on':'Enable desktop reminders'}</button>
      </div>
      <div class="v504Stats">
        ${filterButton('due','Due now',over.length+due.length)}
        ${filterButton('overdue','Overdue',over.length)}
        ${filterButton('waiting','Waiting',waiting.length)}
        ${filterButton('replied','Replies',replied.length)}
        ${filterButton('all','In CRM',sent.length)}
      </div>
      <div class="v504Schedule"><b>Smart timing:</b> first email → 3 working days · first follow-up → 5 working days · later follow-ups → 10 working days. You can override the date before saving.</div>
      <div class="v504List">${rows.length?rows.slice(0,120).map(renderRow).join(''):'<div class="v504Empty">Nothing needs attention in this CRM view.</div>'}</div>`;
    ensureNavBadge();
  }

  function renderRow(r){
    let st=r.state||{},kind=dueKind(r),status=statusText(r),product=r.product||{};
    return `<div class="v504Row ${kind||String(st.stage||'')}">
      <button class="v504RowMain" onclick="v504OpenCrmProspect('${esc(r.id)}')">
        <span><b>${esc(r.company||'Unknown company')}</b><small>${esc(r.sector||'Uncategorised')}${r.email?' · '+esc(r.email):''}</small></span>
        <span><strong>${esc(status)}</strong><small>${esc(product.product_name||'')}</small></span>
      </button>
      <button class="btn" onclick="v504OpenCrmProspect('${esc(r.id)}')">Open</button>
    </div>`;
  }

  function decorateWorkbench(){
    const root=document.getElementById('outWorkbench');if(!root)return;
    const follow=document.getElementById('owFollow');
    const row=selectedRow();
    if(follow&&!follow.value){follow.value=suggestFollowDate(row);follow.dataset.v504Suggested='1'}
    const btn=[...root.querySelectorAll('button')].find(b=>(b.getAttribute('onclick')||'').includes('markOutreachSent'));
    if(btn){
      btn.textContent='Email sent';
      btn.title='Record this email in YMS CRM and schedule the next follow-up';
      if(!btn.dataset.v504Bound){
        btn.dataset.v504Bound='1';
        btn.addEventListener('click',function(){
          const f=document.getElementById('owFollow');if(f&&!f.value)f.value=suggestFollowDate(selectedRow());
          setTimeout(v504RefreshCrm,700);setTimeout(v504RefreshCrm,1800);
        },true);
      }
      if(!root.querySelector('.v504SendHint')){
        const hint=document.createElement('div');hint.className='v504SendHint';hint.innerHTML='<b>CRM:</b> clicking <b>Email sent</b> records the contact, sent email and follow-up date automatically.';btn.insertAdjacentElement('afterend',hint);
      }
    }
  }

  async function refresh(){
    if(typeof api!=='function')return;
    try{
      const rows=await api('/api/outreach/queue?stage=all');
      if(Array.isArray(rows))v504Rows=rows;
      renderDashboard();decorateWorkbench();maybeNotify();
    }catch(_){ensureDashboard();decorateWorkbench()}
  }
  window.v504RefreshCrm=refresh;
  window.v504SetCrmFilter=function(k){v504Filter=k;renderDashboard()};
  window.v504OpenCrmProspect=async function(id){
    try{
      if(typeof showTab==='function')showTab('outreach');
      if(typeof setOutStage==='function')await setOutStage('all');
      if(typeof selectOutreach==='function')await selectOutreach(id);
      setTimeout(()=>document.getElementById('outWorkbench')?.scrollIntoView({behavior:'smooth',block:'start'}),80);
    }catch(_){try{if(typeof openD==='function')openD(id)}catch(__){}}
  };

  window.v504EnableCrmNotifications=async function(){
    if(!('Notification' in window)){renderDashboard();return}
    try{
      let p=Notification.permission;
      if(p!=='granted')p=await Notification.requestPermission();
      if(p==='granted'){localStorage.setItem(V504_KEY,'1');localStorage.removeItem(V504_NOTIFIED)}
      else localStorage.setItem(V504_KEY,'0');
    }catch(_){localStorage.setItem(V504_KEY,'0')}
    renderDashboard();maybeNotify();
  };

  function maybeNotify(){
    if(!('Notification' in window)||Notification.permission!=='granted'||localStorage.getItem(V504_KEY)!=='1')return;
    const due=v504Rows.filter(r=>hasBeenSent(r)&&['overdue','today'].includes(dueKind(r)));
    if(!due.length)return;
    let state={date:'',ids:[]};
    try{state=JSON.parse(localStorage.getItem(V504_NOTIFIED)||'{}')||state}catch(_){state={date:'',ids:[]}}
    if(state.date!==today())state={date:today(),ids:[]};
    const fresh=due.filter(r=>!state.ids.includes(r.id));if(!fresh.length)return;
    const overdue=due.filter(r=>dueKind(r)==='overdue').length;
    const names=fresh.slice(0,3).map(r=>r.company).filter(Boolean).join(', ');
    const body=`${overdue?overdue+' overdue · ':''}${due.length} due now${names?' · '+names:''}`;
    try{
      const n=new Notification(`YMS CRM · ${due.length} follow-up${due.length===1?'':'s'} due`,{body,tag:'yms-crm-followup'});
      n.onclick=()=>{window.focus();try{if(typeof showTab==='function')showTab('outreach')}catch(_){}};
      state.ids=[...new Set([...state.ids,...fresh.map(r=>r.id)])];localStorage.setItem(V504_NOTIFIED,JSON.stringify(state));
    }catch(_){ }
  }

  function boot(){
    ensureDashboard();decorateWorkbench();refresh();
    if(v504RefreshTimer)clearInterval(v504RefreshTimer);
    v504RefreshTimer=setInterval(refresh,5*60*1000);
    window.addEventListener('focus',refresh);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
    let queued=false;
    const mo=new MutationObserver(()=>{if(queued)return;queued=true;setTimeout(()=>{queued=false;ensureDashboard();decorateWorkbench()},120)});
    mo.observe(document.documentElement,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,250));else setTimeout(boot,250);
})();
