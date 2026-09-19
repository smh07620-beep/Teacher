/* Phase 3I · Canonical admin material upload/mutation runtime. */
(function(){
  'use strict';

  window.updateAdminMaterialTypeFields = function(){
    const type=document.getElementById('admin-material-type')?.value||'standard';
    document.getElementById('admin-atlas-fields')?.classList.toggle('hidden',type!=='atlas');
  };

  window.uploadAdminMaterialRequest = function(fd,progressId,fileName,key,status){
    if(!window.MaterialUploadClient?.enqueue) return Promise.reject(new Error('教材上傳元件尚未載入'));
    return window.MaterialUploadClient.enqueue(fd,{headers:{'X-Admin-Key':key},fileName,onProgress:e=>{
        if(status){
          const pct=e.percent;
          status.innerHTML=`⬆️ ${escapeHtml(fileName)}｜安全接收 ${pct}%<span class="block text-[11px] text-slate-500 mt-1">${(e.loaded/1024/1024).toFixed(1)} / ${(e.total/1024/1024).toFixed(1)} MB；接收後會立刻排入背景佇列，不再占住 Web worker。</span>`;
        }
      }});
  };

  window.sha256File = async function(file){
    const buf=await file.arrayBuffer();
    const hash=await crypto.subtle.digest('SHA-256',buf);
    return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
  };

  window.directR2MaterialUpload = async function(file,meta,key,status){
    if(!window.crypto?.subtle) throw new Error('此瀏覽器不支援大型影音安全雜湊直傳');
    status.textContent=`⏳ 正在計算 ${file.name} SHA-256…`;
    const sha256=await window.sha256File(file);
    const init=await fetch('/api/material-upload/init',{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Admin-Key':key},
      body:JSON.stringify({...meta,filename:file.name,size:file.size,sha256,partSizeMb:16})
    });
    const data=await init.json().catch(()=>({}));
    if(!init.ok) throw new Error(data.error||'無法建立大型影音直傳');
    const etags=[];
    for(const part of data.parts||[]){
      const start=(part.partNumber-1)*data.partSize;
      const end=Math.min(file.size,start+data.partSize);
      const res=await fetch(part.url,{method:'PUT',body:file.slice(start,end)});
      if(!res.ok) throw new Error(`R2 第 ${part.partNumber} 段上傳失敗`);
      const etag=res.headers.get('etag');
      if(!etag) throw new Error('R2 未回傳 ETag，請檢查 bucket CORS ExposeHeaders');
      etags.push({partNumber:part.partNumber,etag});
      status.textContent=`⬆️ ${file.name}｜R2 直傳 ${Math.round(end/file.size*100)}%`;
    }
    const done=await fetch(`/api/material-upload/${encodeURIComponent(data.uploadId)}/complete`,{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Admin-Key':key},
      body:JSON.stringify({parts:etags})
    });
    const result=await done.json().catch(()=>({}));
    if(!done.ok) throw new Error(result.error||'R2 直傳完成驗證失敗');
    return result;
  };

  window.adminUploadMaterials = async function(){
    const input=document.getElementById('admin-pptx-upload-input');
    const files=Array.from(input?.files||[]);
    if(!files.length){ alert('請先選擇要上傳的教材檔案。'); return; }
    const key=await getAdminKey();
    if(!key) return;
    const title=document.getElementById('admin-material-title').value.trim();
    const desc=document.getElementById('admin-material-desc').value.trim();
    const group=document.getElementById('admin-material-group').value;
    const category=document.getElementById('admin-material-category').value;
    const status=document.getElementById('admin-upload-status');
    const btn=document.getElementById('admin-upload-btn');
    btn.disabled=true;
    let queued=0;
    const failed=[];
    status.innerHTML=`⏳ 準備安全接收 ${files.length} 份教材…`;
    for(let n=0;n<files.length;n++){
      const file=files[n];
      const progressId=`manual-${Date.now()}-${n}-${Math.random().toString(36).slice(2,8)}`;
      status.innerHTML=`⏳ ${n+1}/${files.length} 接收「${escapeHtml(file.name)}」<span class="block text-[11px] text-slate-500 mt-1">只等待檔案傳到 Render；轉檔、壓縮、MEGA 上傳會在背景繼續。</span>`;
      const area=document.getElementById('admin-material-area')?.value||currentTrainingArea;
      const courseId=document.getElementById('admin-material-course')?.value||'';
      const materialType=document.getElementById('admin-material-type')?.value||'standard';
      const fd=new FormData();
      fd.append('file',file);
      fd.append('title',title);
      fd.append('desc',desc);
      fd.append('category',category);
      fd.append('group',group);
      fd.append('area',area);
      fd.append('courseId',courseId);
      fd.append('materialType',materialType);
      fd.append('progressId',progressId);
      fd.append('atlasCategory',document.getElementById('admin-atlas-category')?.value||'');
      fd.append('atlasMagnification',document.getElementById('admin-atlas-magnification')?.value||'');
      fd.append('atlasInterpretation',document.getElementById('admin-atlas-interpretation')?.value||'');
      fd.append('atlasClinical',document.getElementById('admin-atlas-clinical')?.value||'');
      fd.append('atlasDifferential',document.getElementById('admin-atlas-differential')?.value||'');
      fd.append('atlasNormality',document.getElementById('admin-atlas-normality')?.value||'');
      fd.append('atlasTags',document.getElementById('admin-atlas-tags')?.value||'');
      try{
        const meta={title,desc,category,group,area,courseId,materialType};
        const data=file.size>250*1024*1024
          ? await window.directR2MaterialUpload(file,meta,key,status)
          : await window.uploadAdminMaterialRequest(fd,progressId,file.name,key,status);
        queued++;
        status.innerHTML=`✅ ${n+1}/${files.length}「${escapeHtml(file.name)}」已加入背景佇列<span class="block text-[11px] mt-1">${escapeHtml(data.jobId||'')}｜現在可切換頁面或關閉後台視窗，工作會繼續。</span>`;
      }catch(err){
        failed.push({name:file.name,error:err.message});
        status.innerHTML=`❌ ${escapeHtml(file.name)}：${escapeHtml(err.message)}<span class="block text-[11px] mt-1">其他檔案會繼續接收。</span>`;
      }
    }
    if(failed.length){
      status.innerHTML=`⚠️ 已排入 ${queued}/${files.length} 份；${failed.length} 份接收失敗。<details class="mt-1"><summary class="cursor-pointer font-bold">查看失敗原因</summary><div class="mt-1 space-y-1">${failed.map(x=>`<div>• ${escapeHtml(x.name)}：${escapeHtml(x.error)}</div>`).join('')}</div></details>`;
    } else {
      status.innerHTML=`✅ ${queued} 份教材已安全接收並排入背景工作。你可以離開此頁；完成後會自動出現在教材清單。`;
    }
    input.value='';
    document.getElementById('admin-material-title').value='';
    document.getElementById('admin-material-desc').value='';
    ['admin-atlas-category','admin-atlas-magnification','admin-atlas-interpretation','admin-atlas-clinical','admin-atlas-differential','admin-atlas-tags'].forEach(id=>{
      const el=document.getElementById(id);
      if(el) el.value='';
    });
    btn.disabled=false;
    await renderMaterialJobs(true);
  };

  window.editAdminMaterial = async function(id){
    const materials = await fetchAdminMaterials();
    const m = materials?.find(x => x.id === id);
    if (!m) return;
    const title = prompt('教材名稱：', m.title || '');
    if (title === null) return;
    const desc = prompt('教材說明：', m.desc || '');
    if (desc === null) return;
    const groupOptions = Object.entries(GROUPS).filter(([k,g])=>(m.area||'internal')==='pgy'||!g.pgyOnly).map(([k, g]) => `${k}=${g.label}`).join('、');
    const group = prompt(`所屬組別代碼（${groupOptions}）：`, m.group || 'grpBio');
    if (group === null) return;
    const category = prompt('對應考卷代碼（可於「建立考卷與智慧題庫」查看；留白代表未分類）：', m.category || '');
    if (category === null) return;
    const atlasMeta={...(m.atlasMeta||{})};
    if((m.materialType||'standard')==='atlas'){
      const fields=[['category','圖譜分類'],['magnification','倍率 / 染色'],['interpretation','判讀重點'],['clinical','臨床意義'],['differential','常見鑑別點'],['normality','正／異常標記'],['tags','標籤（逗號分隔）']];
      for(const [k,label] of fields){
        const v=prompt(`${label}：`,atlasMeta[k]||'');
        if(v===null) return;
        atlasMeta[k]=v.trim();
      }
    }
    const key = await getAdminKey();
    const res = await fetch(`/api/slides/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({title,desc,category,group,materialType:m.materialType||'standard',atlasMeta})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '修改失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };

  window.toggleAdminMaterial = async function(id,active){
    const key = await getAdminKey();
    const res = await fetch(`/api/slides/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '更新失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };

  window.deleteAdminMaterial = async function(id){
    if (!confirm('確定刪除這份教材嗎？教材檔案與轉換圖片都會刪除，此操作無法復原。')) return;
    const key = await getAdminKey();
    const res = await fetch(`/api/slides/${id}`, {method:'DELETE',headers:{'X-Admin-Key':key}});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '刪除失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };
})();
