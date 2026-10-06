/* Scoped announcement manager: teacher communication + system notices. */
(function(){
  'use strict';

  const cache={teaching:[],system:[]};
  const courseCache=new Map();
  const editing={teaching:'',system:''};

  function rbac(){return window.TeacherRBAC681||{};}
  function has(permission){const r=rbac();return typeof r.hasPermission==='function'&&r.hasPermission(permission);}
  function canCrossGroup(){return has('education.cross_group.manage');}
  function canSystem(){return has('system.manage');}
  function canTeachAnnouncements(){return has('announcement.manage');}
  function currentUser(){return rbac().user||{};}
  function ownGroup(){return String(currentUser().preferredGroup||window.currentGroupKey||'').trim();}
  function ownArea(){return String(currentUser().preferredArea||window.currentTrainingArea||'internal').trim()||'internal';}
  function esc(value){return typeof window.escapeHtml==='function'?window.escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
  function prefix(kind){return kind==='system'?'system-announcement':'teacher-announcement';}
  function byId(kind,suffix){return document.getElementById(`${prefix(kind)}-${suffix}`);}
  function groupCatalog(){return window.GROUPS||{};}
  function groupLabel(key){const item=groupCatalog()[key]||{};return item.name||item.label||key||'全體';}
  function toLocalInput(value){
    if(!value)return '';
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return '';
    const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);
    return local.toISOString().slice(0,16);
  }
  function toIso(value){
    if(!value)return '';
    const date=new Date(value);
    return Number.isNaN(date.getTime())?'':date.toISOString();
  }
  function activeNow(item){
    if(!item.active)return false;
    const now=Date.now();
    const start=item.startsAt?Date.parse(item.startsAt):0;
    const end=item.endsAt?Date.parse(item.endsAt):0;
    return (!start||start<=now)&&(!end||end>=now);
  }
  function expiringSoon(item){
    if(!activeNow(item)||!item.endsAt)return false;
    const diff=Date.parse(item.endsAt)-Date.now();
    return diff>=0&&diff<=7*86400000;
  }
  function scopeLabel(item){
    if(item.kind==='system')return '全站系統公告';
    if(item.scopeType==='course')return `課程｜${item.courseTitle||item.courseId||'指定課程'}`;
    if(item.scopeType==='group')return `組別｜${groupLabel(item.group)}`;
    return '院內／跨組教學';
  }
  function windowLabel(item){
    const parts=[];
    if(item.startsAt)parts.push(`開始 ${new Date(item.startsAt).toLocaleString('zh-TW',{hour12:false})}`);
    if(item.endsAt)parts.push(`截止 ${new Date(item.endsAt).toLocaleString('zh-TW',{hour12:false})}`);
    return parts.join(' · ');
  }

  function groupOptions(){
    const catalog=groupCatalog();
    const keys=Object.keys(catalog);
    if(!canCrossGroup()){
      const group=ownGroup();
      return group?`<option value="${esc(group)}">${esc(groupLabel(group))}</option>`:'';
    }
    return keys.map(key=>`<option value="${esc(key)}">${esc(groupLabel(key))}</option>`).join('');
  }

  function managerMarkup(kind){
    const system=kind==='system';
    const canCross=canCrossGroup();
    const scopeOptions=system?'':[
      canCross?'<option value="all">跨組／全院教學</option>':'',
      '<option value="group">指定組別</option>',
      '<option value="course">指定課程</option>'
    ].join('');
    const title=system?'系統公告':'公告與通知';
    const subtitle=system
      ?'只發布停機、維護、版本更新、Worker 異常或平台政策；一般教學通知請到教師工作區。'
      :'發布課程與組別教學資訊；首頁與通知中心只顯示學員有權看到的公告。';
    return `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div><p class="admin-page-eyebrow ${system?'text-slate-600':'text-sky-700'}">COMMUNICATION</p><h4 class="text-lg font-black text-slate-950">${system?'🛠️':'📣'} ${title}</h4><p class="mt-1 text-xs text-slate-500 max-w-3xl">${subtitle}</p></div>
        <div class="flex gap-2"><button type="button" data-announcement-refresh class="admin-toolbar-button">↻ 更新</button><button type="button" data-announcement-new class="rounded-xl bg-sky-700 px-4 py-2 text-xs font-black text-white">＋ 發布公告</button></div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><span class="text-[11px] text-slate-500">目前有效</span><strong data-announcement-active class="block mt-1 text-xl text-slate-950">—</strong></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><span class="text-[11px] text-slate-500">即將到期</span><strong data-announcement-expiring class="block mt-1 text-xl text-slate-950">—</strong></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3 col-span-2 sm:col-span-1"><span class="text-[11px] text-slate-500">全部紀錄</span><strong data-announcement-total class="block mt-1 text-xl text-slate-950">—</strong></div>
      </div>
      <div data-announcement-editor class="hidden rounded-2xl border border-sky-100 bg-sky-50/40 p-4 space-y-3">
        <div class="flex items-center justify-between gap-3"><b data-announcement-editor-title class="text-sm text-slate-900">發布公告</b><button type="button" data-announcement-cancel class="text-xs text-slate-500">取消</button></div>
        <div class="grid lg:grid-cols-2 gap-3">
          <label class="text-xs font-bold text-slate-600">公告標題<input data-field="title" maxlength="200" class="learning-input mt-1" placeholder="公告標題"></label>
          ${system?'':`<label class="text-xs font-bold text-slate-600">發布對象<select data-field="scopeType" class="learning-input mt-1">${scopeOptions}</select></label>`}
          ${system?'':`<label data-scope-group class="text-xs font-bold text-slate-600">組別<select data-field="group" class="learning-input mt-1">${groupOptions()}</select></label><label data-scope-course class="hidden text-xs font-bold text-slate-600">課程<select data-field="courseId" class="learning-input mt-1"><option value="">選擇課程…</option></select></label>`}
          <label class="lg:col-span-2 text-xs font-bold text-slate-600">公告內容<textarea data-field="body" rows="3" maxlength="4000" class="learning-input mt-1" placeholder="公告內容"></textarea></label>
          <label class="text-xs font-bold text-slate-600">開始時間（可留空）<input data-field="startsAt" type="datetime-local" class="learning-input mt-1"></label>
          <label class="text-xs font-bold text-slate-600">截止時間（可留空）<input data-field="endsAt" type="datetime-local" class="learning-input mt-1"></label>
        </div>
        <div class="flex flex-wrap gap-4 text-xs text-slate-700"><label class="flex items-center gap-2"><input data-field="pinned" type="checkbox"> 置頂顯示</label><label class="flex items-center gap-2"><input data-field="requireRead" type="checkbox"> 要求在通知中心標記已讀</label></div>
        <div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500">Email 通知仍由既有課程／考核提醒排程負責；公告目前只做站內首頁與通知中心訊息，不會假裝寄出 Email。</div>
        <div class="flex items-center gap-3"><button type="button" data-announcement-save class="rounded-xl bg-sky-700 px-4 py-2 text-xs font-black text-white">發布公告</button><span data-announcement-form-status class="text-xs text-slate-500"></span></div>
      </div>
      <div data-announcement-status class="text-xs text-slate-500">尚未讀取公告。</div>
      <div data-announcement-list class="space-y-2"></div>`;
  }

  function bindManager(section,kind){
    if(section.dataset.announcementBound==='1')return;
    section.dataset.announcementBound='1';
    section.querySelector('[data-announcement-refresh]')?.addEventListener('click',()=>void renderAdminAnnouncements(kind));
    section.querySelector('[data-announcement-new]')?.addEventListener('click',()=>openEditor(kind));
    section.querySelector('[data-announcement-cancel]')?.addEventListener('click',()=>closeEditor(kind));
    section.querySelector('[data-announcement-save]')?.addEventListener('click',()=>void createAdminAnnouncement(kind));
    const scope=section.querySelector('[data-field="scopeType"]');
    scope?.addEventListener('change',()=>void syncScopeEditor(kind));
    section.querySelector('[data-field="group"]')?.addEventListener('change',()=>void loadCourses(kind));
  }

  function ensureSystemManager(){
    if(!canSystem())return null;
    const host=document.getElementById('admin-section-system');
    if(!host)return null;
    let section=document.getElementById('system-announcement-card-1014');
    if(!section){
      section=document.createElement('section');
      section.id='system-announcement-card-1014';
      section.dataset.announcementKind='system';
      section.className='rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4';
      section.innerHTML=managerMarkup('system');
      host.appendChild(section);
    }
    bindManager(section,'system');
    return section;
  }

  function ensureTeacherManager(){
    if(!canTeachAnnouncements())return null;
    const host=document.getElementById('admin-section-content');
    if(!host)return null;
    let section=document.getElementById('teacher-announcement-workspace-1014');
    if(!section){
      section=document.createElement('section');
      section.id='teacher-announcement-workspace-1014';
      section.dataset.announcementKind='teaching';
      section.className='hidden rounded-2xl border border-sky-200 bg-white p-5 shadow-sm space-y-4';
      section.innerHTML=managerMarkup('teaching');
      host.appendChild(section);
    }
    bindManager(section,'teaching');
    return section;
  }

  function hideTeacherSiblings(section){
    const host=section?.parentElement;
    if(!host)return;
    [...host.children].forEach(child=>{
      if(child===section||child.classList.contains('hidden'))return;
      child.dataset.teacherAnnouncementHidden='1';
      child.classList.add('hidden');
    });
  }

  function closeTeacherAnnouncementWorkspace(){
    const section=document.getElementById('teacher-announcement-workspace-1014');
    section?.classList.add('hidden');
    document.querySelectorAll('[data-teacher-announcement-hidden="1"]').forEach(node=>{
      node.classList.remove('hidden');
      delete node.dataset.teacherAnnouncementHidden;
    });
  }

  async function openTeacherAnnouncementWorkspace(){
    const section=ensureTeacherManager();
    if(!section)return false;
    hideTeacherSiblings(section);
    section.classList.remove('hidden');
    const icon=document.getElementById('admin-workspace-icon');
    const title=document.getElementById('admin-workspace-title');
    const summary=document.getElementById('admin-workspace-summary');
    if(icon)icon.textContent='📣';
    if(title)title.textContent='公告與通知 Workspace';
    if(summary)summary.textContent='發布自己授權範圍內的教學公告；首頁與通知中心會依學員組別與課程自動篩選。';
    await renderAdminAnnouncements('teaching');
    return true;
  }

  function openEditor(kind,item=null){
    const section=kind==='system'?ensureSystemManager():ensureTeacherManager();
    if(!section)return;
    editing[kind]=item?.id||'';
    const editor=section.querySelector('[data-announcement-editor]');
    editor?.classList.remove('hidden');
    const set=(name,value)=>{const el=section.querySelector(`[data-field="${name}"]`);if(el)el.value=value??'';};
    const check=(name,value)=>{const el=section.querySelector(`[data-field="${name}"]`);if(el)el.checked=Boolean(value);};
    set('title',item?.title||'');
    set('body',item?.body||'');
    set('startsAt',toLocalInput(item?.startsAt||''));
    set('endsAt',toLocalInput(item?.endsAt||''));
    check('pinned',item?.pinned);
    check('requireRead',item?.requireRead);
    if(kind==='teaching'){
      const defaultScope=canCrossGroup()?'all':'group';
      set('scopeType',item?.scopeType||defaultScope);
      set('group',item?.group||ownGroup());
      void syncScopeEditor(kind,item?.courseId||'');
    }
    const heading=section.querySelector('[data-announcement-editor-title]');
    const save=section.querySelector('[data-announcement-save]');
    if(heading)heading.textContent=item?'編輯公告':'發布公告';
    if(save)save.textContent=item?'儲存修改':'發布公告';
    const status=section.querySelector('[data-announcement-form-status]');
    if(status)status.textContent='';
    editor?.scrollIntoView?.({block:'nearest',behavior:'smooth'});
  }

  function closeEditor(kind){
    const section=kind==='system'?ensureSystemManager():ensureTeacherManager();
    editing[kind]='';
    section?.querySelector('[data-announcement-editor]')?.classList.add('hidden');
  }

  async function loadCourses(kind,selected=''){
    if(kind!=='teaching')return;
    const section=ensureTeacherManager();
    if(!section)return;
    const select=section.querySelector('[data-field="courseId"]');
    const group=section.querySelector('[data-field="group"]')?.value||ownGroup();
    const area=ownArea();
    if(!select)return;
    const key=`${area}|${group}`;
    select.innerHTML='<option value="">讀取課程中…</option>';
    try{
      let rows=courseCache.get(key);
      if(!rows){
        const r=await fetch(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{cache:'no-store'});
        const d=await r.json().catch(()=>[]);
        if(!r.ok)throw new Error(d.error||'課程讀取失敗');
        rows=Array.isArray(d)?d:[];
        courseCache.set(key,rows);
      }
      select.innerHTML='<option value="">選擇課程…</option>'+rows.map(course=>`<option value="${esc(course.id)}">${esc(course.title||course.id)}</option>`).join('');
      if(selected&&[...select.options].some(option=>option.value===selected))select.value=selected;
    }catch(e){
      select.innerHTML='<option value="">課程讀取失敗</option>';
    }
  }

  async function syncScopeEditor(kind,selectedCourse=''){
    if(kind!=='teaching')return;
    const section=ensureTeacherManager();
    if(!section)return;
    const scope=section.querySelector('[data-field="scopeType"]')?.value||'group';
    const groupWrap=section.querySelector('[data-scope-group]');
    const courseWrap=section.querySelector('[data-scope-course]');
    groupWrap?.classList.toggle('hidden',scope==='all');
    courseWrap?.classList.toggle('hidden',scope!=='course');
    if(scope==='course')await loadCourses(kind,selectedCourse);
  }

  function itemRow(item){
    const badges=[
      item.pinned?'📌 置頂':'',
      scopeLabel(item),
      item.requireRead?'需已讀':'',
      activeNow(item)?'● 顯示中':(item.active?'◷ 排程外':'○ 已停用')
    ].filter(Boolean);
    const time=windowLabel(item);
    return `<article data-announcement-id="${esc(item.id)}" class="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div class="min-w-0"><div class="font-bold text-sm text-slate-900">${esc(item.title||'')}</div><div class="mt-1 text-xs text-slate-500 whitespace-pre-wrap">${esc(item.body||'')}</div><div class="mt-2 flex flex-wrap gap-1.5">${badges.map(text=>`<span class="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] text-slate-600">${esc(text)}</span>`).join('')}</div>${time?`<div class="mt-1 text-[10px] text-slate-400">${esc(time)}</div>`:''}</div>
        <div class="flex gap-1.5 shrink-0"><button type="button" data-edit class="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[11px]">編輯</button><button type="button" data-toggle class="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[11px]">${item.active?'停用':'發布'}</button><button type="button" data-delete class="px-2 py-1.5 text-[11px] text-rose-600">刪除</button></div>
      </div></article>`;
  }

  function bindRows(kind,section){
    section.querySelectorAll('[data-announcement-id]').forEach(row=>{
      const id=row.dataset.announcementId;
      const item=cache[kind].find(entry=>String(entry.id)===String(id));
      if(!item)return;
      row.querySelector('[data-edit]')?.addEventListener('click',()=>openEditor(kind,item));
      row.querySelector('[data-toggle]')?.addEventListener('click',()=>void toggleAdminAnnouncement(id,!item.active));
      row.querySelector('[data-delete]')?.addEventListener('click',()=>void deleteAdminAnnouncement(id));
    });
  }

  async function renderAdminAnnouncements(kind){
    const target=kind==='system'?'system':'teaching';
    if(target==='system'&&!canSystem())return;
    if(target==='teaching'&&!canTeachAnnouncements())return;
    const section=target==='system'?ensureSystemManager():ensureTeacherManager();
    if(!section)return;
    const list=section.querySelector('[data-announcement-list]');
    const status=section.querySelector('[data-announcement-status]');
    if(list)list.innerHTML='<div class="text-xs text-slate-400">讀取公告中…</div>';
    try{
      const r=await fetch(`/api/announcements/admin?kind=${encodeURIComponent(target)}`,{cache:'no-store'});
      const rows=await r.json().catch(()=>[]);
      if(!r.ok)throw new Error(rows.error||'公告讀取失敗');
      cache[target]=Array.isArray(rows)?rows:[];
      if(list)list.innerHTML=cache[target].length?cache[target].map(itemRow).join(''):'<div class="text-xs text-slate-400 py-3">尚無公告。</div>';
      const active=cache[target].filter(activeNow).length;
      const expiring=cache[target].filter(expiringSoon).length;
      const setCount=(sel,value)=>{const node=section.querySelector(sel);if(node)node.textContent=String(value);};
      setCount('[data-announcement-active]',active);
      setCount('[data-announcement-expiring]',expiring);
      setCount('[data-announcement-total]',cache[target].length);
      if(status)status.textContent=`共 ${cache[target].length} 則；目前有效 ${active} 則`;
      bindRows(target,section);
    }catch(e){
      if(list)list.innerHTML=`<div class="text-xs text-rose-600">❌ ${esc(e.message)}</div>`;
      if(status)status.textContent='公告讀取失敗';
    }
  }

  async function createAdminAnnouncement(kind='teaching'){
    const target=kind==='system'?'system':'teaching';
    const section=target==='system'?ensureSystemManager():ensureTeacherManager();
    if(!section)return;
    const field=name=>section.querySelector(`[data-field="${name}"]`);
    const payload={
      kind:target,
      title:field('title')?.value.trim()||'',
      body:field('body')?.value.trim()||'',
      active:true,
      startsAt:toIso(field('startsAt')?.value||''),
      endsAt:toIso(field('endsAt')?.value||''),
      pinned:Boolean(field('pinned')?.checked),
      requireRead:Boolean(field('requireRead')?.checked),
      emailEnabled:false
    };
    if(target==='teaching'){
      payload.scopeType=field('scopeType')?.value||'group';
      payload.group=field('group')?.value||ownGroup();
      payload.area=ownArea();
      if(payload.scopeType==='course')payload.courseId=field('courseId')?.value||'';
    }
    const formStatus=section.querySelector('[data-announcement-form-status]');
    if(!payload.title){if(formStatus)formStatus.textContent='❌ 請輸入公告標題';return;}
    if(formStatus)formStatus.textContent='⏳ 儲存中…';
    const editId=editing[target];
    const url=editId?`/api/announcements/${encodeURIComponent(editId)}`:'/api/announcements';
    const r=await fetch(url,{method:editId?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){if(formStatus)formStatus.textContent='❌ '+(d.error||'儲存失敗');return;}
    if(formStatus)formStatus.textContent=editId?'✅ 修改已儲存':'✅ 公告已發布';
    editing[target]='';
    section.querySelector('[data-announcement-editor]')?.classList.add('hidden');
    await renderAdminAnnouncements(target);
  }

  async function toggleAdminAnnouncement(id,active){
    const item=[...cache.teaching,...cache.system].find(entry=>String(entry.id)===String(id));
    const r=await fetch(`/api/announcements/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({active})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){alert(d.error||'更新失敗');return;}
    await renderAdminAnnouncements(item?.kind==='system'?'system':'teaching');
  }

  async function deleteAdminAnnouncement(id){
    if(!confirm('刪除此公告？若只是暫時不顯示，建議使用「停用」。'))return;
    const item=[...cache.teaching,...cache.system].find(entry=>String(entry.id)===String(id));
    const r=await fetch(`/api/announcements/${encodeURIComponent(id)}`,{method:'DELETE'});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){alert(d.error||'刪除失敗');return;}
    await renderAdminAnnouncements(item?.kind==='system'?'system':'teaching');
  }

  window.renderAdminAnnouncements=renderAdminAnnouncements;
  window.createAdminAnnouncement=createAdminAnnouncement;
  window.toggleAdminAnnouncement=toggleAdminAnnouncement;
  window.deleteAdminAnnouncement=deleteAdminAnnouncement;
  window.openTeacherAnnouncementWorkspace=openTeacherAnnouncementWorkspace;
  window.closeTeacherAnnouncementWorkspace=closeTeacherAnnouncementWorkspace;
  window.mountSystemAnnouncementCard=ensureSystemManager;

  function mount(){
    if(canSystem())ensureSystemManager();
    const params=new URLSearchParams(window.location.search);
    if(params.get('admin')==='1'&&params.get('persona')==='teacher'&&params.get('teacherMode')==='announcements'){
      void openTeacherAnnouncementWorkspace();
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
  else mount();
})();
