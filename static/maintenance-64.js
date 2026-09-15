/* Teacher 6.5 M6 · maintenance card using shared AppCore API handling. */
(function(){
  'use strict';

  const C=window.AppCore||{};
  const allowed=new Set([
    'education_admin',
    'system_admin'
  ]);

  async function api(path,options={}){
    if(typeof C.api==='function'){
      return C.api(path,options);
    }

    const response=await fetch(path,{
      credentials:'same-origin',
      ...options
    });

    const data=await response.json().catch(()=>({}));

    if(!response.ok){
      const detail=data?.errorDetail||{};
      const error=new Error(
        detail.message
        ||data?.error
        ||`請求失敗（${response.status}）`
      );

      error.status=response.status;
      error.code=detail.code||'';
      error.data=data;
      error.retryAfter=Number(
        data?.retryAfter
        ||response.headers.get('retry-after')
        ||0
      );

      throw error;
    }

    return data;
  }

  function message(error,fallback='操作失敗，請稍後再試。'){
    if(typeof C.errorMessage==='function'){
      return C.errorMessage(
        error,
        fallback
      );
    }

    return error?.message||fallback;
  }

  async function me(){
    try{
      return await api(
        '/api/auth/me',
        {cache:'no-store'}
      );
    }catch(_error){
      return null;
    }
  }

  function downloadBackup(){
    // File downloads intentionally remain normal browser navigation.
    // The server still performs authentication and authorization.
    window.location.href='/api/maintenance/backup';
  }

  async function restoreBackup(){
    const input=document.getElementById(
      'teacher64-restore-file'
    );

    if(!input?.files?.[0]){
      alert('請先選擇 Teacher 備份 ZIP。');
      return;
    }

    if(!confirm(
      '還原只會補入缺少的資料，不會清空現有資料。確定繼續？'
    )){
      return;
    }

    const button=document.getElementById(
      'teacher64-restore'
    );

    const oldText=button?.textContent||'保守還原';

    if(button){
      button.disabled=true;
      button.textContent='還原中…';
    }

    const fd=new FormData();
    fd.append('file',input.files[0]);
    fd.append('confirm','RESTORE');

    try{
      const data=await api(
        '/api/maintenance/restore',
        {
          method:'POST',
          body:fd
        }
      );

      const summary=Object.entries(
        data.restored||{}
      ).map(
        ([key,value])=>`${key} ${value}`
      ).join('、');

      alert(
        summary
          ?`還原完成：${summary}`
          :'還原完成。'
      );

      input.value='';
    }catch(error){
      console.error(
        'Teacher maintenance restore failed',
        {
          status:error?.status||0,
          code:error?.code||'',
          requestId:error?.requestId||''
        }
      );

      alert(
        message(
          error,
          '還原失敗。'
        )
      );
    }finally{
      if(button){
        button.disabled=false;
        button.textContent=oldText;
      }
    }
  }

  async function init(){
    const auth=await me();
    const role=auth?.user?.role||'';

    if(!allowed.has(role)){
      return;
    }

    if(document.getElementById(
      'teacher64-maintenance'
    )){
      return;
    }

    const host=document.getElementById('admin-section-system');
    if(!host) return;

    const box=document.createElement('section');

    box.id='teacher64-maintenance';
    box.className=
      'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm my-5';

    box.innerHTML=`
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="font-black text-slate-900">
            🛡️ 資料保護與維護
          </h2>
          <p class="text-xs text-slate-500 mt-1">
            邏輯備份、保守還原、上傳檔案驗證與 AI 去識別已啟用。
          </p>
        </div>
        <button
          id="teacher64-backup"
          class="px-4 py-2 rounded-xl bg-slate-900 text-white text-sm font-bold">
          下載系統備份
        </button>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-2">
        <input
          id="teacher64-restore-file"
          type="file"
          accept=".zip"
          class="text-sm">

        <button
          id="teacher64-restore"
          class="px-4 py-2 rounded-xl border border-slate-300 text-sm font-bold">
          保守還原
        </button>

        <span class="text-[11px] text-slate-500">
          只補入缺少資料，不覆蓋現有紀錄。
        </span>
      </div>
    `;

    host.prepend(box);

    document.getElementById(
      'teacher64-backup'
    ).onclick=downloadBackup;

    document.getElementById(
      'teacher64-restore'
    ).onclick=restoreBackup;
  }

  if(document.readyState==='loading'){
    document.addEventListener(
      'DOMContentLoaded',
      init
    );
  }else{
    init();
  }
})();
