/* Teacher 7.1 M4 · Notification Center
 * Actionable rows come from one server-side notification-event projection shared
 * with email delivery. Only personal read/unread markers are mutated here.
 */
(function(){
  'use strict';
  const ID='notification-center-71';
  let currentRows=[];
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  function stableHash(value){let hash=2166136261;for(const char of String(value??'')){hash^=char.charCodeAt(0);hash=Math.imul(hash,16777619);}return(hash>>>0).toString(36);}
  function announcementKey(item){return `announcement:${String(item?.id||'')}:${stableHash(`${item?.title||''}\n${item?.body||''}\n${item?.publishedAt||''}`)}`.slice(0,240);}

  function mount(){
    const existing=document.getElementById(ID);if(existing)return existing;
    const statusHost=document.getElementById('learning-status-detail-71');
    const course=document.getElementById('course-overview');
    const host=course||document.querySelector('main.flex-grow')||document.querySelector('main');
    if(!host)return null;
    const section=document.createElement('details');section.id=ID;section.className='rounded-xl border border-amber-100 bg-amber-50/20 px-3 py-3';
    section.innerHTML=`<summary class="cursor-pointer list-none flex items-center justify-between gap-3"><span><b class="text-sm text-slate-900">🔔 通知中心</b><span id="notification-status-71" class="ml-2 text-[11px] text-slate-500">讀取中…</span></span><span class="text-[11px] font-bold text-amber-700">展開 ▾</span></summary><div class="mt-3 flex justify-end gap-3"><button id="notification-mark-all-read-71" type="button" class="text-[10px] font-bold text-slate-600">全部標示已讀</button><button id="notification-refresh-71" type="button" class="text-[10px] font-bold text-amber-700">↻ 更新</button></div><div id="notification-list-71" class="space-y-2 mt-3"></div><p class="text-[10px] text-slate-400 mt-3">需要處理的通知與 Email 共用同一個伺服器事件來源；公告只在站內顯示。這裡只保存你的已讀狀態，不會修改課程、成績、評量或 Worker 工作。</p>`;
    const grid=document.getElementById('course-overview-grid');if(statusHost)statusHost.appendChild(section);else if(grid)grid.after(section);else if(course)course.appendChild(section);else host.appendChild(section);
    section.querySelector('#notification-refresh-71')?.addEventListener('click',()=>load(true));
    section.querySelector('#notification-mark-all-read-71')?.addEventListener('click',markAllRead);
    return section;
  }

  async function getJSON(url){const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});const data=await response.json().catch(()=>null);if(!response.ok){const error=new Error(data?.error||`讀取失敗（${response.status}）`);error.status=response.status;throw error;}return data;}
  async function patchStates(keys,read){const response=await fetch('/api/notification-states',{method:'PATCH',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({keys,read})});const data=await response.json().catch(()=>null);if(!response.ok)throw new Error(data?.error||`通知狀態更新失敗（${response.status}）`);return data?.states||{};}
  async function readStates(rows){const keys=rows.map(row=>row.key).filter(Boolean);if(!keys.length)return{};const query=new URLSearchParams();keys.forEach(key=>query.append('key',key));const data=await getJSON(`/api/notification-states?${query.toString()}`);return data?.states||{};}

  function announcementRows(data){const rows=Array.isArray(data)?data:(Array.isArray(data?.items)?data.items:[]);return rows.slice(0,5).map(item=>({key:announcementKey(item),persona:'info',kind:'announcement',title:item?.title||'平台公告',detail:item?.body||'平台有新的公告。',badge:'公告',overdue:false,href:'',channels:['in_app'],emailPolicy:'none'}));}
  function actionLabel(item){if(item.kind==='review')return'前往批改';if(item.kind==='material_failure')return'查看教材工作';if(item.kind==='retraining'||item.kind==='material')return'前往教材';if(item.kind==='course'||item.kind==='due'||item.kind==='draft')return'前往課程';if(item.kind==='exam')return'前往考核';return'前往處理';}

  function render(rows){
    const status=document.getElementById('notification-status-71'),list=document.getElementById('notification-list-71');if(!status||!list)return;
    const unread=rows.filter(row=>!row.read).length,urgent=rows.filter(row=>row.overdue).length,actionable=rows.filter(row=>row.kind!=='announcement').length,info=rows.filter(row=>row.kind==='announcement').length;
    status.textContent=rows.length?`${unread} 未讀 · ${actionable} 待處理 · ${urgent} 逾期 · ${info} 公告`:'沒有新通知';
    const markAll=document.getElementById('notification-mark-all-read-71');if(markAll)markAll.disabled=!unread;
    if(!rows.length){list.innerHTML='<div class="rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-700">✓ 目前沒有需要注意的新事項。</div>';return;}
    list.innerHTML=rows.map((item,index)=>`<article class="rounded-xl border ${item.overdue?'border-rose-200 bg-rose-50/50':item.read?'border-slate-100 bg-slate-50/70':'border-slate-200 bg-white'} px-3 py-2 flex items-start justify-between gap-3 flex-wrap ${item.read?'opacity-80':''}"><div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap">${item.read?'':'<span class="inline-block h-2 w-2 rounded-full bg-amber-500" aria-label="未讀"></span>'}<span class="text-xs font-black text-slate-900">${escapeHtml(item.title)}</span><span class="text-[10px] rounded-full ${item.overdue?'bg-rose-100 text-rose-700':'bg-amber-50 text-amber-700'} px-2 py-0.5 font-bold">${escapeHtml(item.badge||'通知')}</span></div><p class="text-[11px] text-slate-500 mt-1 line-clamp-2">${escapeHtml(item.detail||'')}</p></div><div class="flex items-center gap-2 flex-wrap shrink-0"><button type="button" data-notification-read="${index}" class="text-[10px] font-bold px-2 py-1.5 rounded-lg border border-slate-200 text-slate-600 bg-white">${item.read?'標示未讀':'標示已讀'}</button>${item.href?`<a href="${escapeHtml(item.href)}" class="text-xs font-bold px-3 py-2 rounded-xl bg-amber-600 text-white">${escapeHtml(actionLabel(item))}</a>`:''}</div></article>`).join('');
    list.querySelectorAll('[data-notification-read]').forEach(button=>button.addEventListener('click',toggleRead));
  }

  async function updateRead(keys,read){if(!keys.length)return;await patchStates(keys,read);const wanted=new Set(keys);currentRows=currentRows.map(row=>wanted.has(row.key)?{...row,read}:row);render(currentRows);}
  async function toggleRead(event){const index=Number(event.currentTarget?.dataset?.notificationRead),item=currentRows[index];if(!item?.key)return;event.currentTarget.disabled=true;try{await updateRead([item.key],!item.read);}catch(error){alert(error.message||'通知狀態更新失敗');event.currentTarget.disabled=false;}}
  async function markAllRead(){const keys=currentRows.filter(row=>!row.read).map(row=>row.key).filter(Boolean);if(!keys.length)return;const button=document.getElementById('notification-mark-all-read-71');if(button)button.disabled=true;try{await updateRead(keys,true);}catch(error){alert(error.message||'通知狀態更新失敗');if(button)button.disabled=false;}}

  async function load(force=false){
    const section=mount();if(!section)return;const status=document.getElementById('notification-status-71');if(status)status.textContent=force?'更新中…':'讀取中…';
    try{
      const [events,announcements]=await Promise.all([getJSON('/api/training-command-center/notifications'),getJSON('/api/announcements?limit=5').catch(()=>[])]);
      const rows=[...(Array.isArray(events?.items)?events.items:[]),...announcementRows(announcements)];
      const states=await readStates(rows);currentRows=rows.map(row=>({...row,read:Boolean(states[row.key]?.read)}));render(currentRows);document.documentElement.dataset.notificationSource='training-command-center';
    }catch(error){if(error?.status===401||error?.status===403){section.classList.add('hidden');return;}if(status)status.textContent=`❌ ${error.message||'通知讀取失敗'}`;}
  }

  function init(){if(mount())load(false);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  window.TeacherNotificationCenter71=Object.freeze({load});
})();
