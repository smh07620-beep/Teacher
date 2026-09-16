/* Phase 3B · Admin course/material module.
 * Loaded after the legacy admin bundle.  Extracted globals intentionally keep
 * the historical window contract so existing inline handlers and sibling
 * bundles keep working while system-admin.js is reduced incrementally.
 */
(function(){
  'use strict';

  function adminCourseRowHTML(c, optimistic=false){
    return `<div data-course-id="${escapeHtml(c.id||'')}" class="flex justify-between items-center bg-white border ${optimistic?'border-violet-300 ring-2 ring-violet-100':'border-violet-100'} rounded-lg px-3 py-2 transition-all"><div><div class="text-sm font-semibold flex items-center gap-2">${escapeHtml(c.title||'')}${optimistic?'<span class="text-[10px] px-2 py-0.5 rounded-full bg-violet-50 text-violet-700">剛建立</span>':''}</div><div class="text-xs text-slate-400">${escapeHtml(c.desc||'')}</div></div><button onclick="adminDeleteCourse('${c.id}')" class="text-xs text-rose-600">刪除</button></div>`;
  }

  function paintAdminCourses(list, optimisticId=''){
    const box=document.getElementById('admin-courses-list');
    if(!box) return;
    box.innerHTML=list.length
      ? '<div class="text-xs font-bold text-violet-800">既有課程</div>'+list.map(c=>adminCourseRowHTML(c,c.id===optimisticId)).join('')
      : '<div class="text-xs text-slate-400">目前無課程</div>';
  }

  function optimisticInsertAdminCourse(course, area, group){
    const k=adminScopeKey(area,group);
    const old=adminCoursesCache.get(k)?.data||[];
    const list=[course,...old.filter(c=>c.id!==course.id)];
    adminCoursesCache.set(k,{data:list,at:Date.now()});
    const currentArea=document.getElementById('wizard-area')?.value||'pgy';
    const currentGroup=document.getElementById('wizard-group')?.value||'grpBio';
    if(currentArea===area&&currentGroup===group) paintAdminCourses(list,course.id);
  }

  async function refreshAdminMaterialCourses(){
    const sel=document.getElementById('admin-material-course');
    if(!sel) return;
    const area=document.getElementById('admin-material-area')?.value||currentTrainingArea;
    const group=document.getElementById('admin-material-group')?.value||currentGroupKey;
    const res=await fetch(`/api/courses?area=${area}&group=${group}`);
    const cs=res.ok?await res.json():[];
    sel.innerHTML='<option value="">未指定課程</option>'+cs.map(c=>`<option value="${c.id}">${escapeHtml(c.title)}</option>`).join('');
  }

  async function renderAdminCourses(force=false){
    const key=await getAdminKey();
    if(!key) return;
    const box=document.getElementById('admin-courses-list');
    if(!box) return;
    const area=document.getElementById('wizard-area')?.value||'pgy';
    const group=document.getElementById('wizard-group')?.value||'grpBio';
    const k=adminScopeKey(area,group);
    const cached=adminCoursesCache.get(k);
    const now=Date.now();
    if(cached?.data) paintAdminCourses(cached.data);
    if(!force && cached?.data && (now-cached.at)<ADMIN_COURSE_CACHE_MS){
      refreshAdminMaterialCourses();
      return;
    }
    if(!cached?.data) box.innerHTML='<div class="text-xs text-slate-400 animate-pulse">讀取課程中…</div>';
    else box.classList.add('opacity-70');
    try{
      const res=await fetch(`/api/courses/admin?area=${area}&group=${group}`,{headers:{'X-Admin-Key':key}});
      const cs=await res.json().catch(()=>[]);
      if(!res.ok) throw new Error(cs.error||'讀取課程失敗');
      const list=Array.isArray(cs)?cs:[];
      adminCoursesCache.set(k,{data:list,at:Date.now()});
      paintAdminCourses(list);
    }catch(e){
      if(!cached?.data) box.innerHTML=`<div class="text-xs text-rose-500">❌ ${escapeHtml(e.message)}</div>`;
    }finally{
      box.classList.remove('opacity-70');
      refreshAdminMaterialCourses();
    }
  }

  async function adminDeleteCourse(id){
    if(!confirm('刪除課程？教材與考卷不會刪除，只會解除課程關聯。')) return;
    const key=await getAdminKey();
    if(!key) return;
    const r=await fetch(`/api/courses/${id}`,{method:'DELETE',headers:{'X-Admin-Key':key}});
    if(!r.ok){ alert('刪除失敗'); return; }
    await renderAdminCourses(true);
    await renderAdminCourseMaterialHub(true);
  }

  window.adminCourseRowHTML=adminCourseRowHTML;
  window.paintAdminCourses=paintAdminCourses;
  window.optimisticInsertAdminCourse=optimisticInsertAdminCourse;
  window.renderAdminCourses=renderAdminCourses;
  window.refreshAdminMaterialCourses=refreshAdminMaterialCourses;
  window.adminDeleteCourse=adminDeleteCourse;
})();
