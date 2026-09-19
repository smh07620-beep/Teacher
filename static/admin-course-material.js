/* Phase 3B · Canonical admin course/material module.
 * Exported globals preserve historical inline-handler and sibling-module contracts.
 */
(function(){
  'use strict';

  function adminCourseRowHTML(c, optimistic=false){
    return `<div data-course-id="${escapeHtml(c.id||'')}" class="flex justify-between items-center bg-white border ${optimistic?'border-violet-300 ring-2 ring-violet-100':'border-violet-100'} rounded-lg px-3 py-2 transition-all"><div><div class="text-sm font-semibold flex items-center gap-2">${escapeHtml(c.title||'')}${optimistic?'<span class="text-[10px] px-2 py-0.5 rounded-full bg-violet-50 text-violet-700">剛建立</span>':''}</div><div class="text-xs text-slate-400">${escapeHtml(c.desc||'')}</div></div><button data-csp-click="adminDeleteCourse('${c.id}')" class="text-xs text-rose-600">刪除</button></div>`;
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
    const res=await fetch(`/api/courses?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`);
    const cs=res.ok?await res.json():[];
    sel.innerHTML='<option value="">未指定課程</option>'+cs.map(c=>`<option value="${c.id}">${escapeHtml(c.title)}</option>`).join('');
  }

  async function renderAdminCourses(force=false){
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
      const res=await fetch(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{});
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
    const r=await fetch(`/api/courses/${id}`,{method:'DELETE',});
    if(!r.ok){ alert('刪除失敗'); return; }
    await renderAdminCourses(true);
    renderAdminCourseMaterialHub(true);
  }

  window.adminCourseRowHTML=adminCourseRowHTML;
  window.paintAdminCourses=paintAdminCourses;
  window.optimisticInsertAdminCourse=optimisticInsertAdminCourse;
  window.renderAdminCourses=renderAdminCourses;
  window.refreshAdminMaterialCourses=refreshAdminMaterialCourses;
  window.adminDeleteCourse=adminDeleteCourse;

  // Final convergence: canonical owner migrated from system-admin.js.
  function adminMaterialTypeBadge(m){
      const meta={standard:['📚','教材'],video:['🎬','影音'],atlas:['🔬','Atlas'],infographic:['📊','圖表'],troubleshooting:['🧰','錯誤分析'],case:['🩸','案例'],sop:['📑','SOP']}[m.materialType]||['📄','教材'];
      return `${meta[0]} ${meta[1]}`;
  }

  function adminHubMaterialRow(m){
      return `<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-2 rounded-xl bg-slate-50 border border-slate-100 px-3 py-2.5"><div class="min-w-0"><div class="text-xs font-bold text-slate-800 truncate">${escapeHtml(m.title||m.filename||'未命名教材')}</div><div class="text-[10px] text-slate-500 mt-1">${adminMaterialTypeBadge(m)}${m.categoryLabel?' · 對應：'+escapeHtml(m.categoryLabel):''}${m.active===false?' · 已停用':''}</div></div>${m.isBuiltin?'':`<div class="flex gap-1.5 shrink-0"><button data-csp-click="editAdminMaterial('${m.id}')" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-indigo-600 text-white">編輯</button><button data-csp-click="toggleAdminMaterial('${m.id}',${m.active?'false':'true'})" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-amber-500 text-white">${m.active?'停用':'啟用'}</button></div>`}</div>`;
  }

  function paintAdminCourseMaterialHub(box,state){
      if(!box)return;
      const {area,group}=state;
      const courses=Array.isArray(state.courses)?state.courses:[];
      const materials=Array.isArray(state.materials)?state.materials:[];
      const cats=Array.isArray(state.cats)?state.cats:[];
      const scoped=materials.filter(m=>(m.area||'internal')===area&&(m.group||'grpBio')===group);
      const cards=[];
      for(const c of courses){
          const mats=teachingOrderedMaterials(c,scoped.filter(m=>m.courseId===c.id));
          const exams=cats.filter(q=>q.courseId===c.id);
          const qcount=exams.reduce((n,q)=>n+examBankCount(q),0);
          const materialChip=state.loading.materials?`📚 教材 ${mats.length} 份 · 同步中`:`📚 教材 ${mats.length} 份`;
          const examChip=state.loading.cats?`📋 考卷 ${exams.length} 份 · 同步中`:`📋 考卷 ${exams.length} 份`;
          cards.push(`<details class="group rounded-2xl border border-violet-100 bg-white overflow-hidden" ${c.id===box.dataset.lastCreated?'open':''}><summary class="cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3 hover:bg-violet-50/50 transition-colors"><div class="min-w-0"><div class="font-black text-sm text-slate-900 truncate">📘 ${escapeHtml(c.title||'未命名課程')}</div>${c.desc&&c.desc.trim()!==c.title?.trim()?`<div class="text-[11px] text-slate-500 mt-1">${escapeHtml(c.desc)}</div>`:''}<div class="flex flex-wrap gap-1.5 mt-2"><span class="course-stat-chip">${materialChip}</span><span class="course-stat-chip">📝 題庫 ${qcount} 題</span><span class="course-stat-chip">${examChip}</span></div></div><div class="flex items-center gap-2 shrink-0"><span class="course-stat-chip">${c.active?"已啟用":"已停用"}</span><button data-csp-click="event.preventDefault();event.stopPropagation();teachingEditCourse('${c.id}')" class="teaching-primary">編排課程</button><button data-csp-click="event.preventDefault();event.stopPropagation();adminDeleteCourse('${c.id}')" class="text-[10px] text-rose-600 px-2 py-1">刪除課程</button></div></summary><div class="border-t border-violet-50 p-4 grid lg:grid-cols-2 gap-4"><div><div class="text-xs font-black text-slate-700 mb-2">📚 教材</div><div class="space-y-2">${mats.length?mats.map(adminHubMaterialRow).join(''):(state.loading.materials?'<div class="text-xs text-slate-400 animate-pulse">教材資料同步中…</div>':'<div class="text-xs text-slate-400">尚未關聯教材</div>')}</div></div><div><div class="text-xs font-black text-slate-700 mb-2">📋 考卷與出題設定</div><div class="space-y-2">${exams.length?exams.map(q=>`<div class="rounded-xl bg-indigo-50/60 border border-indigo-100 px-3 py-2.5"><div class="flex items-start justify-between gap-2"><div><div class="text-xs font-bold text-indigo-950">${escapeHtml(q.title||'未命名考卷')}</div><div class="flex flex-wrap gap-1.5 mt-1.5"><span class="text-[10px] text-indigo-700">👤 ${escapeHtml(examAudienceLabel(q))}</span><span class="text-[10px] text-indigo-700">🧠 題庫 ${examBankCount(q)} 題</span><span class="text-[10px] text-indigo-700">📋 ${escapeHtml(examDrawLabel(q))}</span><span class="text-[10px] text-indigo-700">🎯 ${Number(q.passingScore||80)} 分</span>${q.blindMode?'<span class="text-[10px] text-slate-700">🕶️ 盲測</span>':''}</div></div><button data-csp-click="jumpToAdminQuiz('${q.id}','${area}','${group}')" class="text-[10px] bg-indigo-700 text-white rounded-lg px-2.5 py-1.5 shrink-0">管理題庫</button></div></div>`).join(''):(state.loading.cats?'<div class="text-xs text-slate-400 animate-pulse">考卷資料同步中…</div>':'<div class="text-xs text-slate-400">尚未建立考卷</div>')}</div></div></div></details>`);
      }
      const unassigned=state.loading.courses?[]:scoped.filter(m=>!m.courseId);
      const orphanExams=state.loading.courses?[]:cats.filter(q=>!q.courseId);
      const pending=[];
      if(state.loading.courses)pending.push('課程');
      if(state.loading.materials)pending.push('教材');
      if(state.loading.cats)pending.push('考卷');
      const errors=Object.entries(state.errors).filter(([,value])=>value).map(([key,value])=>`${{courses:'課程',materials:'教材',cats:'考卷'}[key]||key}：${value}`);
      const status=pending.length?`背景同步：${pending.join('、')}`:'✓ 已同步';
      const empty=cards.length?cards.join(''):(state.loading.courses?'<div class="text-xs text-slate-400 py-3 animate-pulse">正在讀取課程…</div>':'<div class="text-xs text-slate-400 py-3">目前尚無課程。</div>');
      box.innerHTML=`<div class="rounded-2xl border border-violet-200 bg-violet-50/40 p-4"><div class="flex items-center justify-between gap-3"><div><h5 class="font-black text-violet-950">🗂️ 課程 → 教材 → 題庫 → 考卷</h5><p class="text-[11px] text-violet-700 mt-1">先顯示已取得的資料；較慢的教材與考卷狀態會在背景補齊。</p><div class="mt-1 text-[10px] ${pending.length?'text-violet-500':'text-emerald-600'}">${escapeHtml(status)}</div></div><button data-csp-click="renderAdminCourseMaterialHub(true)" class="text-[10px] px-3 py-1.5 rounded-lg bg-white border border-violet-200 text-violet-700">↻ 更新</button></div>${errors.length?`<div class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700">⚠️ ${errors.map(escapeHtml).join('；')}。其他已載入內容仍可使用。</div>`:''}<div class="mt-3 space-y-2">${empty}${(!state.loading.courses&&(unassigned.length||orphanExams.length))?`<details class="rounded-2xl border border-amber-100 bg-white overflow-hidden"><summary class="cursor-pointer list-none px-4 py-3 font-bold text-xs text-amber-800">📁 通用／未歸類：教材 ${unassigned.length} 份 · 考卷 ${orphanExams.length} 份</summary><div class="p-4 border-t border-amber-50 space-y-2">${unassigned.map(adminHubMaterialRow).join('')}${orphanExams.map(q=>`<div class="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs"><b>📝 ${escapeHtml(q.title)}</b> · ${escapeHtml(examDrawLabel(q))} · 及格 ${Number(q.passingScore||80)} 分</div>`).join('')}</div></details>`:''}</div></div>`;
      box.dataset.ready='1';
  }

  async function renderAdminCourseMaterialHub(force=false){
      const box=document.getElementById('admin-course-material-hub');
      if(!box)return;
      const area=document.getElementById('wizard-area')?.value||currentTrainingArea;
      const group=document.getElementById('wizard-group')?.value||currentGroupKey;
      const key=adminScopeKey(area,group);
      const courseCache=adminCoursesCache.get(key);
      const materialCache=Array.isArray(adminMaterialsCache.data)?adminMaterialsCache.data:[];
      const state={
          area,group,
          courses:Array.isArray(courseCache?.data)?courseCache.data:[],
          materials:materialCache,
          cats:[],
          loading:{
              courses:!(Array.isArray(courseCache?.data)&&!force&&(Date.now()-courseCache.at)<ADMIN_COURSE_CACHE_MS),
              materials:!(Array.isArray(adminMaterialsCache.data)&&!force&&(Date.now()-adminMaterialsCache.at)<ADMIN_CACHE_MS),
              cats:true
          },
          errors:{courses:'',materials:'',cats:''}
      };
      paintAdminCourseMaterialHub(box,state);
      const jobs=[];

      if(state.loading.courses){
          jobs.push(fetch(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{})
              .then(async res=>{const data=await res.json().catch(()=>[]);if(!res.ok)throw new Error(data.error||'讀取課程失敗');state.courses=Array.isArray(data)?data:[];adminCoursesCache.set(key,{data:state.courses,at:Date.now()});})
              .catch(error=>{state.errors.courses=error.message||'讀取失敗';})
              .finally(()=>{state.loading.courses=false;paintAdminCourseMaterialHub(box,state);}));
      }

      if(state.loading.materials){
          jobs.push(Promise.resolve(fetchAdminMaterials(force))
              .then(data=>{if(Array.isArray(data))state.materials=data;else if(data==null)throw new Error('教材清單未回傳資料');})
              .catch(error=>{state.errors.materials=error.message||'讀取失敗';})
              .finally(()=>{state.loading.materials=false;paintAdminCourseMaterialHub(box,state);}));
      }

      jobs.push(fetch(`/api/quiz-categories?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{credentials:'same-origin',cache:'no-store'})
          .then(async res=>{const data=await res.json().catch(()=>[]);if(!res.ok)throw new Error(data.error||'讀取考卷失敗');state.cats=Array.isArray(data)?data:[];})
          .catch(error=>{state.errors.cats=error.message||'讀取失敗';})
          .finally(()=>{state.loading.cats=false;paintAdminCourseMaterialHub(box,state);}));

      // Presentation refresh is deliberately nonblocking. Keep a handle for
      // diagnostics without forcing every caller to wait for a slow provider.
      box._adminCourseMaterialRefresh=Promise.allSettled(jobs);
      return state;
  }

  window.adminMaterialTypeBadge=adminMaterialTypeBadge;
  window.adminHubMaterialRow=adminHubMaterialRow;
  window.paintAdminCourseMaterialHub=paintAdminCourseMaterialHub;
  window.renderAdminCourseMaterialHub=renderAdminCourseMaterialHub;
})();
