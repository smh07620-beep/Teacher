/* Phase 3D · Canonical admin announcements module.
 * Window exports preserve the existing inline-handler contracts.
 */
(function(){
  'use strict';

  async function renderAdminAnnouncements(){
    const box=document.getElementById('admin-announcement-list');
    const status=document.getElementById('admin-announcement-status');
    if(!box) return;
    const key=await getAdminKey();
    if(!key) return;
    box.innerHTML='<div class="text-xs text-slate-400">讀取公告中…</div>';
    try{
      const r=await fetch('/api/announcements/admin',{headers:{'X-Admin-Key':key},cache:'no-store'});
      const rows=await r.json().catch(()=>[]);
      if(!r.ok) throw new Error(rows.error||'公告讀取失敗');
      box.innerHTML=rows.length?rows.map(a=>`<div class="rounded-xl border border-slate-200 bg-slate-50 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div class="min-w-0"><div class="font-bold text-sm text-slate-900">${escapeHtml(a.title||'')}</div><div class="text-xs text-slate-500 mt-1 whitespace-pre-wrap">${escapeHtml(a.body||'')}</div><div class="text-[10px] mt-1 ${a.active?'text-emerald-700':'text-slate-400'}">${a.active?'● 已發布':'○ 已停用'} · ${escapeHtml((a.publishedAt||a.createdAt||'').slice(0,16).replace('T',' '))}</div></div><div class="flex gap-2 shrink-0"><button onclick="toggleAdminAnnouncement('${a.id}',${a.active?'false':'true'})" class="text-xs border border-slate-300 bg-white px-3 py-1.5 rounded-lg">${a.active?'停用':'發布'}</button><button onclick="deleteAdminAnnouncement('${a.id}')" class="text-xs text-rose-600 px-2 py-1.5">更多：刪除</button></div></div>`).join(''):'<div class="text-xs text-slate-400 py-3">尚無公告。</div>';
      if(status) status.textContent=`共 ${rows.length} 則公告`;
    }catch(e){
      box.innerHTML=`<div class="text-xs text-rose-600">❌ ${escapeHtml(e.message)}</div>`;
    }
  }

  async function createAdminAnnouncement(){
    const title=document.getElementById('admin-announcement-title')?.value.trim()||'';
    const body=document.getElementById('admin-announcement-body')?.value.trim()||'';
    const status=document.getElementById('admin-announcement-status');
    if(!title){ if(status) status.textContent='❌ 請輸入公告標題'; return; }
    const key=await getAdminKey();
    if(!key) return;
    if(status) status.textContent='⏳ 發布中…';
    const r=await fetch('/api/announcements',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({title,body,active:true})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){ if(status) status.textContent='❌ '+(d.error||'發布失敗'); return; }
    document.getElementById('admin-announcement-title').value='';
    document.getElementById('admin-announcement-body').value='';
    if(status) status.textContent='✅ 公告已發布到首頁';
    await renderAdminAnnouncements();
  }

  async function toggleAdminAnnouncement(id,active){
    const key=await getAdminKey();
    if(!key) return;
    const r=await fetch(`/api/announcements/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})});
    if(!r.ok){ const d=await r.json().catch(()=>({})); alert(d.error||'更新失敗'); return; }
    await renderAdminAnnouncements();
  }

  async function deleteAdminAnnouncement(id){
    if(!confirm('刪除此公告？這是永久刪除；若只是暫時不顯示，請使用「停用」。')) return;
    const key=await getAdminKey();
    if(!key) return;
    const r=await fetch(`/api/announcements/${encodeURIComponent(id)}`,{method:'DELETE',headers:{'X-Admin-Key':key}});
    if(!r.ok){ const d=await r.json().catch(()=>({})); alert(d.error||'刪除失敗'); return; }
    await renderAdminAnnouncements();
  }

  window.renderAdminAnnouncements=renderAdminAnnouncements;
  window.createAdminAnnouncement=createAdminAnnouncement;
  window.toggleAdminAnnouncement=toggleAdminAnnouncement;
  window.deleteAdminAnnouncement=deleteAdminAnnouncement;
})();
