/* Teacher 6.4 maintenance card: backup/restore and privacy policy status. */
(function(){
  'use strict';
  const allowed=new Set(['education_admin','system_admin']);
  async function me(){try{const r=await fetch('/api/auth/me');return r.ok?await r.json():null}catch(_e){return null}}
  function downloadBackup(){window.location.href='/api/maintenance/backup';}
  async function restoreBackup(){
    const input=document.getElementById('teacher64-restore-file');
    if(!input?.files?.[0]) return alert('請先選擇 Teacher 備份 ZIP。');
    if(!confirm('還原只會補入缺少的資料，不會清空現有資料。確定繼續？')) return;
    const fd=new FormData();fd.append('file',input.files[0]);fd.append('confirm','RESTORE');
    const r=await fetch('/api/maintenance/restore',{method:'POST',body:fd});
    const data=await r.json().catch(()=>({}));
    if(!r.ok) return alert(data.error||'還原失敗');
    alert('還原完成：'+Object.entries(data.restored||{}).map(([k,v])=>`${k} ${v}`).join('、'));
  }
  async function init(){
    const auth=await me(), role=auth?.user?.role||''; if(!allowed.has(role)) return;
    if(document.getElementById('teacher64-maintenance')) return;
    const host=document.querySelector('main')||document.body;
    const box=document.createElement('section');box.id='teacher64-maintenance';box.className='rounded-2xl border border-slate-200 bg-white p-5 shadow-sm my-5';
    box.innerHTML=`<div class="flex flex-wrap items-center justify-between gap-3"><div><h2 class="font-black text-slate-900">🛡️ 6.4 資料保護與維護</h2><p class="text-xs text-slate-500 mt-1">邏輯備份、保守還原、上傳檔案驗證與 AI 去識別已啟用。</p></div><button id="teacher64-backup" class="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm font-bold">下載系統備份</button></div><div class="mt-4 flex flex-wrap items-center gap-2"><input id="teacher64-restore-file" type="file" accept=".zip" class="text-sm"><button id="teacher64-restore" class="px-4 py-2 rounded-xl border border-slate-300 text-sm font-bold">保守還原</button><span class="text-[11px] text-slate-500">只補入缺少資料，不覆蓋現有紀錄。</span></div>`;
    host.prepend(box);
    document.getElementById('teacher64-backup').onclick=downloadBackup;
    document.getElementById('teacher64-restore').onclick=restoreBackup;
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
