/* Phase 3I · Canonical admin material upload/mutation runtime. */
(function(){
  'use strict';

  window.updateAdminMaterialTypeFields = function(){
    const type=document.getElementById('admin-material-type')?.value||'standard';
    document.getElementById('admin-atlas-fields')?.classList.toggle('hidden',type!=='atlas');
  };

  window.uploadAdminMaterialRequest = function(fd,progressId,fileName,status){
    if(!window.MaterialUploadClient?.enqueue) return Promise.reject(new Error('教材上傳元件尚未載入'));
    return window.MaterialUploadClient.enqueue(fd,{fileName,onProgress:e=>{
        if(status){
          const pct=e.percent;
          status.innerHTML=`⬆️ ${escapeHtml(fileName)}｜安全接收 ${pct}%<span class="block text-[11px] text-slate-500 mt-1">${(e.loaded/1024/1024).toFixed(1)} / ${(e.total/1024/1024).toFixed(1)} MB；接收後會立刻排入背景佇列，不再占住 Web worker。</span>`;
        }
      }});
  };

  window.sha256File = async function(file){
    if(!window.MaterialUploadClient?.sha256Blob) throw new Error('教材上傳元件尚未載入');
    return window.MaterialUploadClient.sha256Blob(file);
  };

  window.directR2MaterialUpload = async function(file,meta,status){
    if(!window.MaterialUploadClient?.directUpload) throw new Error('教材上傳元件尚未載入');
    const fd=new FormData();
    fd.append('file',file);
    Object.entries(meta||{}).forEach(([name,value])=>fd.append(name,String(value??'')));
    return window.MaterialUploadClient.directUpload(fd,{fileName:file.name,onProgress:e=>{
      if(status) status.textContent=`⬆️ ${file.name}｜R2 直傳 ${e.percent}%`;
    }});
  };

  window.adminUploadMaterials = async function(){
    const input=document.getElementById('admin-pptx-upload-input');
    const files=Array.from(input?.files||[]);
    if(!files.length){ alert('請先選擇要上傳的教材檔案。'); return; }
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
      status.innerHTML=`⏳ ${n+1}/${files.length} 接收「${escapeHtml(file.name)}」<span class="block text-[11px] text-slate-500 mt-1">只等待檔案傳到雲端暫存；轉檔、壓縮、正式儲存會在背景繼續。</span>`;
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
        const data=await window.uploadAdminMaterialRequest(fd,progressId,file.name,status);
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
    const res = await fetch(`/api/slides/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,desc,category,group,materialType:m.materialType||'standard',atlasMeta})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '修改失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };

  window.toggleAdminMaterial = async function(id,active){
    const res = await fetch(`/api/slides/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({active})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '更新失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };

  window.publishMaterialVersion = async function(id){
    const materials = await fetchAdminMaterials();
    const material = materials?.find(x=>x.id===id);
    if(!material) return alert('找不到教材資料。');
    const nextVersion = Number(material.currentVersion||1)+1;
    const reason = prompt(`發布 V${nextVersion}｜請輸入本次版本變更原因：`, '');
    if(reason===null) return;
    if(!reason.trim()) return alert('版本變更原因不可空白。');
    const requiresRetraining = confirm('這次改版是否要求相關學員重新完成教育訓練？\n\n「確定」＝要求重訓；「取消」＝保留既有完成資格。');
    const finalMessage = requiresRetraining
      ? `將發布 V${nextVersion}，並把相關學員既有完成狀態標記為需重新訓練。歷史完成紀錄不會刪除。\n\n確定繼續？`
      : `將發布 V${nextVersion}，既有完成資格仍有效。\n\n確定繼續？`;
    if(!confirm(finalMessage)) return;
    const res = await fetch(`/api/slides/${encodeURIComponent(id)}/versions`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      credentials:'same-origin',
      body:JSON.stringify({changeReason:reason.trim(),requiresRetraining})
    });
    const data=await res.json().catch(()=>({}));
    if(!res.ok) return alert(data.error||'版本發布失敗');
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    alert(`✅ 已發布 V${Number(data.version||nextVersion)}${requiresRetraining?'，並要求重新訓練。':'。'}`);
  };

  window.viewMaterialVersions = async function(id){
    const res=await fetch(`/api/slides/${encodeURIComponent(id)}/versions`,{credentials:'same-origin'});
    const data=await res.json().catch(()=>[]);
    if(!res.ok) return alert(data.error||'讀取版本紀錄失敗');
    const rows=Array.isArray(data)?data:[];
    if(!rows.length) return alert('目前沒有版本紀錄。');
    const text=rows.slice(0,20).map(v=>{
      const retraining=v.requiresRetraining?'｜要求重訓':'';
      const who=v.publishedBy?`｜${v.publishedBy}`:'';
      const when=v.publishedAt?`｜${v.publishedAt}`:'';
      return `V${Number(v.version||1)}${retraining}${who}${when}\n${v.changeReason||'未填寫變更原因'}`;
    }).join('\n\n');
    alert(`教材版本紀錄\n\n${text}`);
  };

  window.deleteAdminMaterial = async function(id){
    if (!confirm('確定刪除這份教材嗎？教材檔案與轉換圖片都會刪除，此操作無法復原。')) return;
    const res = await fetch(`/api/slides/${id}`, {method:'DELETE',});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '刪除失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };
})();
