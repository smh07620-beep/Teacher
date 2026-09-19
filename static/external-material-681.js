/* Canonical create/edit client for safe external teaching media. */
(function(){
  'use strict';

  async function api(url,options={}){
    if(typeof window.AppCore?.api==='function') return window.AppCore.api(url,options);
    const response=await fetch(url,{credentials:'same-origin',...options});
    const data=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(data.error||'操作失敗');
    return data;
  }

  async function create(body){
    return api('/api/materials/external',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)
    });
  }

  async function link(materialId,url){
    return api(`/api/materials/${encodeURIComponent(materialId)}/external-media`,{
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url})
    });
  }

  window.ExternalMediaClient=Object.freeze({create,link});

  function setOptions(id,items,empty){
    const el=document.getElementById(id);
    if(!el)return;
    el.innerHTML=`<option value="">${empty}</option>`+(items||[]).map(x=>
      `<option value="${String(x.id).replace(/"/g,'&quot;')}">${window.escapeHtml?window.escapeHtml(x.title||x.id):x.title||x.id}</option>`
    ).join('');
  }

  window.openExternalMaterialCreateDrawer=async function(){
    const drawer=document.getElementById('external-material-drawer');
    if(!drawer)return;
    drawer.classList.remove('hidden');
    try{
      const area=document.getElementById('admin-material-area')?.value||'internal';
      const group=document.getElementById('admin-material-group')?.value||window.currentGroupKey||'grpBio';
      document.getElementById('external-material-area').value=area;
      const groupSelect=document.getElementById('external-material-group');
      groupSelect.innerHTML=[...document.querySelectorAll('#admin-material-group option')].map(o=>
        `<option value="${o.value}" ${o.value===group?'selected':''}>${o.textContent}</option>`
      ).join('');
      const [courses,categories]=await Promise.all([
        api(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`),
        api(`/api/quiz-categories/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`)
      ]);
      setOptions('external-material-course',courses,'未指定課程');
      setOptions('external-material-category',categories,'未指定考卷');
    }catch(error){
      document.getElementById('external-material-preview').textContent='❌ '+error.message;
    }
  };

  window.createExternalMaterialFromDrawer=async function(){
    const preview=document.getElementById('external-material-preview');
    try{
      const body={
        title:document.getElementById('external-material-title').value.trim(),
        description:document.getElementById('external-material-description').value.trim(),
        area:document.getElementById('external-material-area').value,
        group:document.getElementById('external-material-group').value,
        courseId:document.getElementById('external-material-course').value,
        category:document.getElementById('external-material-category').value,
        url:document.getElementById('external-material-url').value.trim()
      };
      preview.textContent='⏳ 驗證 provider 並建立教材…';
      const created=await create(body);
      preview.textContent=`✅ 已建立 ${created.material?.title||'外部教材'}（${created.externalMedia?.provider||'external'}）；未使用 Worker 或物件儲存。`;
      if(typeof window.invalidateAdminMaterialsCache==='function') window.invalidateAdminMaterialsCache();
      return created;
    }catch(error){
      preview.textContent='❌ '+error.message;
      return null;
    }
  };

  window.closeExternalMaterialCreateDrawer=function(){
    document.getElementById('external-material-drawer')?.classList.add('hidden');
  };
})();
