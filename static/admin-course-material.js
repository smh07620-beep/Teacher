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
    if(!confirm('確定刪除這門課程嗎？\n\n只會刪除課程本身；教材與考卷都會保留，並移到「通用／未歸類」。之後可以重新關聯到其他課程，或另外刪除教材。')) return;
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

  function canSystemPurgeMaterial(){
      const r=window.TeacherRBAC681||{};
      const roles=r.roles instanceof Set?r.roles:new Set(Array.isArray(r.roles)?r.roles:[]);
      return roles.has('system_admin')&&typeof r.hasPermission==='function'&&r.hasPermission('system.manage');
  }

  function adminHubMaterialRow(m){
      const version=Math.max(1,Number(m.currentVersion||1));
      return `<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-2 rounded-xl bg-slate-50 border border-slate-100 px-3 py-2.5"><div class="min-w-0"><div class="flex flex-wrap items-center gap-1.5"><div class="text-xs font-bold text-slate-800 truncate">${escapeHtml(m.title||m.filename||'未命名教材')}</div><span class="rounded-full bg-white border border-slate-200 px-1.5 py-0.5 text-[9px] font-black text-slate-600">V${version}</span></div><div class="text-[10px] text-slate-500 mt-1">${adminMaterialTypeBadge(m)}${m.categoryLabel?' · 對應：'+escapeHtml(m.categoryLabel):''}${m.active===false?' · 已停用':''}</div></div>${m.isBuiltin?'':`<div class="flex flex-wrap gap-1.5 shrink-0"><button data-csp-click="editAdminMaterial('${m.id}')" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-indigo-600 text-white">管理教材</button><button data-csp-click="prepareMaterialVersionUpload('${m.id}')" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-teal-700 text-white">上傳新版</button><button data-csp-click="viewMaterialVersions('${m.id}')" class="text-[10px] px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700">版本紀錄</button><button data-csp-click="toggleAdminMaterial('${m.id}',${m.active?'false':'true'})" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-amber-500 text-white">${m.active?'停用':'啟用'}</button><button type="button" data-material-course-link="${escapeHtml(m.id||'')}" class="text-[10px] px-2.5 py-1.5 rounded-lg border border-teal-200 bg-white font-bold text-teal-800">${m.courseId?'更換課程':'歸入課程'}</button><button data-csp-click="deleteAdminMaterial('${m.id}')" class="text-[10px] px-2.5 py-1.5 rounded-lg border border-rose-300 bg-rose-50 font-bold text-rose-700">🗑️ 刪除教材</button>${canSystemPurgeMaterial()?`<button type="button" data-material-purge-check="${escapeHtml(m.id||'')}" title="系統管理員用：清除無任何引用的實體儲存" class="text-[10px] px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white text-slate-500">系統永久清除…</button>`:''}</div>`}</div>`;
  }

  function ensureMaterialPurgeDialog(){
      let dialog=document.getElementById('material-purge-dialog');
      if(dialog)return dialog;
      dialog=document.createElement('dialog');dialog.id='material-purge-dialog';dialog.className='v561-profile-dialog';
      dialog.innerHTML='<form class="v561-profile-card" method="dialog"><div class="v561-profile-head"><div><strong>系統永久清除教材</strong><span>僅系統管理員可使用；與一般「刪除教材」不同，這裡會檢查並清除無引用的實體儲存。</span></div><button type="button" data-purge-close aria-label="關閉">×</button></div><div data-purge-body class="space-y-3"></div><div class="v561-profile-actions"><button type="button" class="secondary" data-purge-close>關閉</button><button type="button" data-purge-submit class="hidden">系統永久清除</button></div></form>';
      document.body.appendChild(dialog);
      dialog.querySelectorAll('[data-purge-close]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
      dialog.querySelector('[data-purge-submit]')?.addEventListener('click',async()=>{
          const state=dialog._purgeState||{},input=dialog.querySelector('[data-purge-confirmation]');
          if(!state.token||!input)return;
          const button=dialog.querySelector('[data-purge-submit]');button.disabled=true;button.textContent='系統永久清除中…';
          try{
              const response=await fetch('/api/slides/'+encodeURIComponent(state.id)+'/purge',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmationToken:state.token,confirmationText:input.value})});
              const data=await response.json().catch(()=>({}));
              if(!response.ok)throw new Error(data.error||'永久清除失敗');
              dialog.close();await window.fetchAdminMaterials?.();await renderAdminCourseMaterialHub(true);
          }catch(error){const status=dialog.querySelector('[data-purge-status]');if(status)status.textContent='❌ '+(error.message||'永久清除失敗');button.disabled=false;button.textContent='系統永久清除';}
      });
      return dialog;
  }

  async function inspectMaterialPurge(materialId){
      if(!canSystemPurgeMaterial())return;
      const dialog=ensureMaterialPurgeDialog(),body=dialog.querySelector('[data-purge-body]'),submit=dialog.querySelector('[data-purge-submit]');
      dialog._purgeState={id:materialId,token:''};submit?.classList.add('hidden');
      body.innerHTML='<div class="text-xs text-slate-500">正在重新檢查版本、PowerPoint、影片與發布引用…</div>';
      if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
      try{
          const response=await fetch('/api/slides/'+encodeURIComponent(materialId)+'/purge-readiness',{credentials:'same-origin',cache:'no-store'});
          const data=await response.json().catch(()=>({}));
          if(!response.ok)throw new Error(data.error||'無法檢查永久清除條件');
          const blockers=Array.isArray(data.blockers)?data.blockers:[];
          if(!data.purgeAllowed){
              body.innerHTML='<div class="rounded-xl border border-amber-200 bg-amber-50 p-3"><b class="text-sm text-amber-900">目前不能永久清除</b><p class="mt-1 text-xs text-amber-800">仍有 '+Number(data.blockerCount||0)+' 筆引用。請先保留此教材，避免破壞歷史紀錄或已產生內容。</p></div><div class="space-y-1">'+blockers.map(item=>'<div class="text-xs text-slate-600">'+escapeHtml(item.type||'reference')+'：'+Number(item.count||0)+' 筆'+(item.artifactCount?'（artifact '+Number(item.artifactCount)+'）':'')+'</div>').join('')+'</div>';
              return;
          }
          dialog._purgeState={id:materialId,token:data.confirmationToken||''};
          body.innerHTML='<div class="rounded-xl border border-rose-200 bg-rose-50 p-3"><b class="text-sm text-rose-900">引用檢查已通過</b><p class="mt-1 text-xs text-rose-800">確認權杖僅短時間有效。送出時伺服器會再次檢查所有引用。</p></div><label class="block text-xs font-bold text-slate-700">輸入教材名稱「'+escapeHtml(data.confirmationText||materialId)+'」確認<input data-purge-confirmation autocomplete="off" class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"></label><p data-purge-status class="text-xs text-slate-500">永久清除後無法從教材版本歷程復原。</p>';
          submit?.classList.remove('hidden');
      }catch(error){body.innerHTML='<div class="text-xs text-rose-700">❌ '+escapeHtml(error.message||'檢查失敗')+'</div>';}
  }

  function learningAssignmentAudienceLabel(item){
      if(item?.assigneeType==='all')return '全體人員';
      if(item?.assigneeType==='group')return `組別：${item.assigneeKey||item.group||''}`;
      return `學員：${item?.assigneeKey||''}`;
  }

  function ensureLearningAssignmentDialog(){
      let dialog=document.getElementById('learning-assignment-dialog');
      if(dialog)return dialog;
      dialog=document.createElement('dialog');
      dialog.id='learning-assignment-dialog';
      dialog.className='v561-profile-dialog';
      dialog.innerHTML=`<form id="learning-assignment-form" class="v561-profile-card">
        <div class="v561-profile-head"><div><strong>指派學習</strong><span id="learning-assignment-course-title">建立一般院內課程指派</span></div><button type="button" id="learning-assignment-close" aria-label="關閉">×</button></div>
        <div id="learning-assignment-existing" class="space-y-2 mb-4"></div>
        <label><span>指派對象</span><select id="learning-assignment-audience-type"><option value="group">目前組別</option><option value="user">指定學員帳號</option><option value="all">全體人員</option></select></label>
        <label id="learning-assignment-audience-key-wrap"><span id="learning-assignment-audience-key-label">組別</span><input id="learning-assignment-audience-key" autocomplete="off"></label>
        <label><span>學習要求</span><select id="learning-assignment-requirement"><option value="required">指定完成</option><option value="elective">自由選讀</option></select></label>
        <label><span>完成期限</span><input id="learning-assignment-due-at" type="date"></label>
        <p id="learning-assignment-status" class="v561-profile-status">建立後會出現在學員首頁、我的待辦與通知中心。</p>
        <div class="v561-profile-actions"><button type="button" id="learning-assignment-cancel" class="secondary">取消</button><button type="submit">建立指派</button></div>
      </form>`;
      document.body.appendChild(dialog);
      const close=()=>{try{dialog.close();}catch(_){dialog.removeAttribute('open');}};
      dialog.querySelector('#learning-assignment-close')?.addEventListener('click',close);
      dialog.querySelector('#learning-assignment-cancel')?.addEventListener('click',close);
      dialog.addEventListener('click',event=>{if(event.target===dialog)close();});
      const type=dialog.querySelector('#learning-assignment-audience-type');
      const syncAudience=()=>{
          const value=type?.value||'group';
          const input=dialog.querySelector('#learning-assignment-audience-key');
          const label=dialog.querySelector('#learning-assignment-audience-key-label');
          if(!input||!label)return;
          if(value==='all'){
              input.value='';input.disabled=true;label.textContent='全體人員';
          }else if(value==='user'){
              input.disabled=false;input.value='';label.textContent='學員帳號';input.placeholder='請輸入 username';
          }else{
              input.disabled=false;input.value=dialog._assignmentState?.group||currentGroupKey||'grpBio';label.textContent='組別';input.placeholder='';
          }
      };
      type?.addEventListener('change',syncAudience);
      dialog.querySelector('#learning-assignment-form')?.addEventListener('submit',async event=>{
          event.preventDefault();
          const ctx=dialog._assignmentState||{};
          const status=dialog.querySelector('#learning-assignment-status');
          const assigneeType=dialog.querySelector('#learning-assignment-audience-type')?.value||'group';
          const assigneeKey=assigneeType==='all'?'':(dialog.querySelector('#learning-assignment-audience-key')?.value||'').trim();
          const requirement=dialog.querySelector('#learning-assignment-requirement')?.value||'required';
          const body={courseId:ctx.courseId||'',assigneeType,assigneeKey,required:requirement==='required',dueAt:dialog.querySelector('#learning-assignment-due-at')?.value||''};
          if(status)status.textContent='建立指派中…';
          try{
              const response=await fetch('/api/learning-assignments',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
              const data=await response.json().catch(()=>({}));
              if(!response.ok)throw new Error(data.error||'建立指派失敗');
              if(status)status.textContent='✓ 指派已建立';
              close();
              await renderAdminCourseMaterialHub(true);
          }catch(error){if(status)status.textContent=`❌ ${error.message||'建立指派失敗'}`;}
      });
      dialog._syncAssignmentAudience=syncAudience;
      return dialog;
  }

  function paintExistingAssignments(dialog,state,courseId){
      const host=dialog.querySelector('#learning-assignment-existing');
      if(!host)return;
      const rows=(Array.isArray(state.assignments)?state.assignments:[]).filter(item=>item.courseId===courseId&&item.active!==false);
      host.innerHTML=rows.length
        ? `<div class="text-xs font-black text-slate-700">目前有效指派</div>${rows.map(item=>`<div class="rounded-xl border border-teal-100 bg-teal-50/40 px-3 py-2 flex items-center justify-between gap-2"><div><b class="text-xs text-slate-800">${escapeHtml(learningAssignmentAudienceLabel(item))}</b><div class="text-[10px] text-slate-500 mt-1">${item.required===false?'自由選讀':'指定完成'}${item.dueAt?` · 期限 ${escapeHtml(String(item.dueAt).slice(0,10))}`:' · 未設定期限'}</div></div><button type="button" data-learning-assignment-cancel="${escapeHtml(item.id||'')}" class="text-[10px] text-rose-700 px-2 py-1">取消指派</button></div>`).join('')}`
        : '<div class="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">目前沒有有效指派。</div>';
      host.querySelectorAll('[data-learning-assignment-cancel]').forEach(button=>button.addEventListener('click',async()=>{
          const id=button.dataset.learningAssignmentCancel||'';
          if(!id||!confirm('取消這筆課程指派？既有學習紀錄不會刪除。'))return;
          button.disabled=true;
          try{
              const response=await fetch(`/api/learning-assignments/${encodeURIComponent(id)}`,{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({active:false})});
              const data=await response.json().catch(()=>({}));
              if(!response.ok)throw new Error(data.error||'取消指派失敗');
              try{dialog.close();}catch(_){dialog.removeAttribute('open');}
              await renderAdminCourseMaterialHub(true);
          }catch(error){alert(error.message||'取消指派失敗');button.disabled=false;}
      }));
  }

  function openLearningAssignmentDialog(courseId,state){
      const course=(state.courses||[]).find(item=>item.id===courseId);
      if(!course)return;
      const dialog=ensureLearningAssignmentDialog();
      dialog._assignmentState={courseId,group:state.group,area:state.area};
      const title=dialog.querySelector('#learning-assignment-course-title');if(title)title.textContent=`${course.title||'課程'} · ${state.area==='pgy'?'PGY':'院內'} / ${state.group}`;
      const type=dialog.querySelector('#learning-assignment-audience-type');if(type)type.value='group';
      const due=dialog.querySelector('#learning-assignment-due-at');if(due)due.value='';
      const requirement=dialog.querySelector('#learning-assignment-requirement');if(requirement)requirement.value='required';
      const status=dialog.querySelector('#learning-assignment-status');if(status)status.textContent='建立後會出現在學員首頁、我的待辦與通知中心。';
      dialog._syncAssignmentAudience?.();
      paintExistingAssignments(dialog,state,courseId);
      if(typeof dialog.showModal==='function'&&!dialog.open)dialog.showModal();else dialog.setAttribute('open','');
  }

  function ensureMaterialCourseLinkDialog(){
      let dialog=document.getElementById('material-course-link-dialog');
      if(dialog)return dialog;
      dialog=document.createElement('dialog');
      dialog.id='material-course-link-dialog';
      dialog.className='v561-profile-dialog';
      dialog.innerHTML='<form class="v561-profile-card"><div class="v561-profile-head"><div><strong>教材歸入課程</strong><span>可把刪除課程後留下的未關聯教材重新掛到新課程；掛入課程時會同步啟用，課程正式發布後學員即可看到。</span></div><button type="button" data-course-link-close aria-label="關閉">×</button></div><label class="block text-xs font-bold text-slate-700">目標課程<select data-course-link-select class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"></select></label><p data-course-link-status class="mt-2 text-xs text-slate-500"></p><div class="v561-profile-actions"><button type="button" class="secondary" data-course-link-close>取消</button><button type="submit">儲存關聯</button></div></form>';
      document.body.appendChild(dialog);
      const close=()=>{try{dialog.close();}catch(_){dialog.removeAttribute('open');}};
      dialog.querySelectorAll('[data-course-link-close]').forEach(button=>button.addEventListener('click',close));
      dialog.querySelector('form')?.addEventListener('submit',async event=>{
          event.preventDefault();
          const ctx=dialog._courseLinkState||{},select=dialog.querySelector('[data-course-link-select]'),status=dialog.querySelector('[data-course-link-status]');
          const courseId=String(select?.value||'');
          const button=dialog.querySelector('button[type="submit"]');
          if(button)button.disabled=true;
          if(status)status.textContent='儲存教材關聯中…';
          try{
              const response=await fetch('/api/slides/'+encodeURIComponent(ctx.materialId||''),{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({courseId,active:courseId?true:ctx.active!==false})});
              const data=await response.json().catch(()=>({}));
              if(!response.ok)throw new Error(data.error||'教材關聯更新失敗');
              window.invalidateAdminMaterialsCache?.();
              close();
              await renderAdminCourseMaterialHub(true);
              await window.renderAdminMaterials?.(true);
          }catch(error){
              if(status)status.textContent='❌ '+(error.message||'教材關聯更新失敗');
          }finally{if(button)button.disabled=false;}
      });
      return dialog;
  }

  function openMaterialCourseLinkDialog(materialId,box){
      const state=box?._adminCourseMaterialState||box?._learningAssignmentState||{};
      const material=(state.materials||[]).find(item=>String(item.id||'')===String(materialId||''));
      if(!material)return alert('找不到教材資料，請重新整理後再試。');
      const courses=(state.courses||[]).filter(course=>String(course.group||'')===String(material.group||state.group||'')&&String(course.area||'')===String(material.area||state.area||''));
      const dialog=ensureMaterialCourseLinkDialog(),select=dialog.querySelector('[data-course-link-select]'),status=dialog.querySelector('[data-course-link-status]');
      dialog._courseLinkState={materialId:String(material.id||''),active:material.active!==false};
      select.replaceChildren(new Option('通用／未歸類（不掛課程）',''),...courses.map(course=>new Option(course.title||course.id,String(course.id||''))));
      select.value=courses.some(course=>String(course.id||'')===String(material.courseId||''))?String(material.courseId||''):'';
      if(status)status.textContent=material.courseId?'目前已掛入課程；可改到其他課程或設為未歸類。':'目前是未關聯教材，請選擇要掛入的課程。';
      if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
  }

  function bindMaterialCourseLinkControls(box){
      if(!box||box.dataset.materialCourseLinkBound==='1')return;
      box.dataset.materialCourseLinkBound='1';
      box.addEventListener('click',event=>{
          const button=event.target.closest?.('[data-material-course-link]');
          if(!button)return;
          event.preventDefault();event.stopPropagation();
          openMaterialCourseLinkDialog(button.dataset.materialCourseLink||'',box);
      });
  }

  function bindMaterialPurgeControls(box){
      if(!box||box.dataset.materialPurgeBound==='1')return;
      box.dataset.materialPurgeBound='1';
      box.addEventListener('click',event=>{
          const button=event.target.closest?.('[data-material-purge-check]');
          if(!button)return;
          event.preventDefault();event.stopPropagation();
          inspectMaterialPurge(button.dataset.materialPurgeCheck||'');
      });
  }

  function bindLearningAssignmentControls(box,state){
      box._learningAssignmentState=state;
      if(box.dataset.learningAssignmentBound==='1')return;
      box.dataset.learningAssignmentBound='1';
      box.addEventListener('click',event=>{
          const button=event.target.closest?.('[data-learning-assign-course]');
          if(!button)return;
          event.preventDefault();event.stopPropagation();
          openLearningAssignmentDialog(button.dataset.learningAssignCourse||'',box._learningAssignmentState||state);
      });
  }

  async function loadCourseFeedbackSummary(courseId,panel){
      if(!panel||!courseId)return;
      const output=panel.querySelector('[data-course-feedback-summary]');
      if(output)output.innerHTML='<span class="text-slate-400">讀取回饋彙總中…</span>';
      try{
          const res=await fetch(`/api/course-feedback/${encodeURIComponent(courseId)}/summary`,{credentials:'same-origin',cache:'no-store'});
          const data=await res.json().catch(()=>({}));
          if(!res.ok)throw new Error(data.error||'無法讀取回饋彙總');
          const count=Number(data.responseCount||0),average=Number(data.averageRating||0),counts=data.ratingCounts||{};
          if(output)output.innerHTML=`<div class="flex flex-wrap items-center gap-2"><span class="course-stat-chip">回覆 ${count} 份</span><span class="course-stat-chip">平均 ${count?average.toFixed(1):'—'} / 5</span></div><div class="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500">${[5,4,3,2,1].map(score=>`<span>${score} 分：${Number(counts[String(score)]||0)}</span>`).join('')}</div>`;
      }catch(error){
          if(output)output.innerHTML=`<span class="text-amber-700">${escapeHtml(error.message||'無法讀取回饋彙總')}</span>`;
      }
  }

  function appendCourseFeedbackSummaryPanels(box,courses){
      const details=Array.from(box.querySelectorAll('.admin-course-list > details'));
      courses.forEach((course,index)=>{
          const card=details[index],body=card?.querySelector(':scope > div.border-t');
          if(!body)return;
          const panel=document.createElement('div');
          panel.className='lg:col-span-2 rounded-xl border border-teal-100 bg-teal-50/50 px-3 py-3';
          panel.innerHTML='<div class="flex items-center justify-between gap-3"><div><div class="text-xs font-black text-teal-900">💬 課程回饋彙總</div><div class="text-[10px] text-teal-700 mt-0.5">只顯示匿名統計，不列出個別學員與留言。</div></div></div><div data-course-feedback-summary class="mt-2 text-[11px] text-slate-500">尚未讀取</div>';
          const button=document.createElement('button');
          button.type='button';
          button.className='mt-2 rounded-lg border border-teal-200 bg-white px-3 py-1.5 text-[10px] font-bold text-teal-800';
          button.textContent='查看回饋彙總';
          button.addEventListener('click',()=>loadCourseFeedbackSummary(course.id,panel));
          panel.firstElementChild?.appendChild(button);
          body.appendChild(panel);
      });
  }

  async function jumpToAdminQuiz(quizId,area,group){
      const targetArea=String(area||currentTrainingArea||'internal');
      const targetGroup=String(group||currentGroupKey||'grpBio');
      const areaSelect=document.getElementById('admin-quiz-area');
      const groupSelect=document.getElementById('admin-quiz-group');
      if(areaSelect)areaSelect.value=targetArea;
      if(groupSelect){
          if(typeof window.groupOptionsForArea==='function'){
              groupSelect.innerHTML=window.groupOptionsForArea(targetArea);
          }
          if([...groupSelect.options].some(option=>option.value===targetGroup)){
              groupSelect.value=targetGroup;
          }
      }
      await Promise.resolve(window.switchAdminWorkspace?.('assessment',true));
      await Promise.resolve(window.renderAdminQuizCategories?.(true));
      const panel=document.getElementById(`qpanel-${quizId}`);
      if(!panel){alert('找不到這份考卷，請重新整理後再試。');return;}
      if(panel.classList.contains('hidden')){
          await Promise.resolve(window.toggleQuizQuestionsPanel?.(quizId));
      }
      panel.scrollIntoView({behavior:'smooth',block:'start'});
  }

  function paintAdminCourseMaterialHub(box,state){
      if(!box)return;
      bindMaterialPurgeControls(box);
      bindMaterialCourseLinkControls(box);
      const {area,group}=state;
      const courses=Array.isArray(state.courses)?state.courses:[];
      const visibleLimit=Math.max(30,Number(box.dataset.courseVisibleLimit)||30);
      const visibleCourses=courses.slice(0,visibleLimit);
      const materials=Array.isArray(state.materials)?state.materials:[];
      const cats=Array.isArray(state.cats)?state.cats:[];
      const scoped=materials.filter(m=>(m.area||'internal')===area&&(m.group||'grpBio')===group);
      const cards=[];
      for(const c of visibleCourses){
          const mats=teachingOrderedMaterials(c,scoped.filter(m=>m.courseId===c.id));
          const exams=cats.filter(q=>q.courseId===c.id);
          const qcount=exams.reduce((n,q)=>n+examBankCount(q),0);
          const assignments=(Array.isArray(state.assignments)?state.assignments:[]).filter(item=>item.courseId===c.id&&item.active!==false);
          const materialChip=state.loading.materials?`📚 教材 ${mats.length} 份 · 同步中`:`📚 教材 ${mats.length} 份`;
          const examChip=state.loading.cats?`📋 考卷 ${exams.length} 份 · 同步中`:`📋 考卷 ${exams.length} 份`;
          const assignmentChip=state.loading.assignments?'👥 指派 · 同步中':`👥 指派 ${assignments.length} 筆`;
          const lifecycle=String(c.lifecycleStatus||(c.active?'published':'draft'));
          const lifecycleLabel=({draft:'草稿',ready:'可發布',published:'已發布',ended:'已結束',archived:'已封存'})[lifecycle]||lifecycle;
          const assignmentButton=state.assignmentAccess===false||lifecycle!=='published'?'':`<button type="button" data-learning-assign-course="${escapeHtml(c.id||'')}" class="text-[10px] rounded-lg bg-teal-700 text-white px-2.5 py-1.5">指派學習</button>`;
          cards.push(`<details data-course-id="${escapeHtml(c.id||'')}" data-course-lifecycle="${escapeHtml(lifecycle)}" class="group rounded-2xl border border-violet-100 bg-white overflow-hidden" ${c.id===box.dataset.lastCreated?'open':''}><summary class="cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3 hover:bg-violet-50/50 transition-colors"><div class="min-w-0"><div class="font-black text-sm text-slate-900 truncate">📘 ${escapeHtml(c.title||'未命名課程')}</div>${c.desc&&c.desc.trim()!==c.title?.trim()?`<div class="text-[11px] text-slate-500 mt-1">${escapeHtml(c.desc)}</div>`:''}<div class="flex flex-wrap gap-1.5 mt-2"><span class="course-stat-chip">${materialChip}</span><span class="course-stat-chip">📝 題庫 ${qcount} 題</span><span class="course-stat-chip">${examChip}</span><span class="course-stat-chip">${assignmentChip}</span></div></div><div class="flex items-center gap-2 shrink-0"><span class="course-stat-chip">${escapeHtml(lifecycleLabel)}</span><span data-course-lifecycle-actions="${escapeHtml(c.id||'')}"></span>${assignmentButton}<button data-csp-click="event.preventDefault();event.stopPropagation();teachingEditCourse('${c.id}')" class="teaching-primary">編排課程</button><button data-csp-click="event.preventDefault();event.stopPropagation();adminDeleteCourse('${c.id}')" class="text-[10px] text-rose-600 px-2 py-1">刪除課程</button></div></summary><div class="border-t border-violet-50 p-4 grid lg:grid-cols-2 gap-4"><div><div class="text-xs font-black text-slate-700 mb-2">📚 教材</div><div class="space-y-2">${mats.length?mats.map(adminHubMaterialRow).join(''):(state.loading.materials?'<div class="text-xs text-slate-400 animate-pulse">教材資料同步中…</div>':'<div class="text-xs text-slate-400">尚未關聯教材</div>')}</div></div><div><div class="text-xs font-black text-slate-700 mb-2">📋 考卷與出題設定</div><div class="space-y-2">${exams.length?exams.map(q=>`<div class="rounded-xl bg-indigo-50/60 border border-indigo-100 px-3 py-2.5"><div class="flex items-start justify-between gap-2"><div><div class="text-xs font-bold text-indigo-950">${escapeHtml(q.title||'未命名考卷')}</div><div class="flex flex-wrap gap-1.5 mt-1.5"><span class="text-[10px] text-indigo-700">👤 ${escapeHtml(examAudienceLabel(q))}</span><span class="text-[10px] text-indigo-700">🧠 題庫 ${examBankCount(q)} 題</span><span class="text-[10px] text-indigo-700">📋 ${escapeHtml(examDrawLabel(q))}</span><span class="text-[10px] text-indigo-700">🎯 ${Number(q.passingScore||80)} 分</span>${q.blindMode?'<span class="text-[10px] text-slate-700">🕶️ 盲測</span>':''}</div></div><button data-csp-click="jumpToAdminQuiz('${q.id}','${area}','${group}')" class="text-[10px] bg-indigo-700 text-white rounded-lg px-2.5 py-1.5 shrink-0">管理題庫</button></div></div>`).join(''):(state.loading.cats?'<div class="text-xs text-slate-400 animate-pulse">考卷資料同步中…</div>':'<div class="text-xs text-slate-400">尚未建立考卷</div>')}</div></div></div></details>`);
      }
      // A summary is a disclosure control, not a toolbar. Keep action buttons
      // outside it so browser accessibility validation and click routing agree.
      for(let index=0;index<cards.length;index+=1){
          cards[index]=cards[index].replace(
              /<div class="flex items-center gap-2 shrink-0">(<span class="course-stat-chip">[^<]*<\/span>)([\s\S]*?)<\/div><\/summary>/,
              (_match,status,actions)=>`${status}</summary><div data-course-card-actions class="flex flex-wrap gap-2 px-4 py-2 border-t border-violet-50">${actions}</div>`
          );
      }
      const unassigned=state.loading.courses?[]:scoped.filter(m=>!m.courseId);
      const orphanExams=state.loading.courses?[]:cats.filter(q=>!q.courseId);
      const pending=[];
      if(state.loading.courses)pending.push('課程');
      if(state.loading.materials)pending.push('教材');
      if(state.loading.cats)pending.push('考卷');
      if(state.loading.assignments)pending.push('指派');
      const errors=Object.entries(state.errors).filter(([,value])=>value).map(([key,value])=>`${{courses:'課程',materials:'教材',cats:'考卷',assignments:'指派'}[key]||key}：${value}`);
      const status=pending.length?`背景同步：${pending.join('、')}`:'✓ 已同步';
      const empty=cards.length?cards.join(''):(state.loading.courses?'<div class="text-xs text-slate-400 py-3 animate-pulse">正在讀取課程…</div>':'<div class="text-xs text-slate-400 py-3">目前尚無課程。</div>');
      const courseCount=state.loading.courses?'—':courses.length;
      const materialCount=state.loading.materials?'—':scoped.length;
      const examCount=state.loading.cats?'—':cats.length;
      const unassignedCount=state.loading.courses?'—':unassigned.length+orphanExams.length;
      box.innerHTML=`<div class="admin-course-dashboard"><div data-product-section="overview" class="admin-course-summary-grid"><div><span>課程</span><strong>${courseCount}</strong><small>目前範圍</small></div><div><span>教材</span><strong>${materialCount}</strong><small>已歸入此組</small></div><div><span>考卷</span><strong>${examCount}</strong><small>含草稿與發布</small></div><div><span>待整理</span><strong>${unassignedCount}</strong><small>未歸類教材／考卷</small></div></div><div class="admin-course-sync-row"><span class="${pending.length?'is-syncing':'is-ready'}">${escapeHtml(status)}</span><span>點開課程即可管理教材、題庫與考卷。</span></div>${errors.length?`<div class="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700">⚠️ ${errors.map(escapeHtml).join('；')}。其他已載入內容仍可使用。</div>`:''}<div data-product-section="current-work" class="admin-course-list mt-4 space-y-2">${empty}${(!state.loading.courses&&(unassigned.length||orphanExams.length))?`<details class="rounded-2xl border border-amber-100 bg-white overflow-hidden"><summary class="cursor-pointer list-none px-4 py-3 font-bold text-xs text-amber-800">📁 通用／未歸類：教材 ${unassigned.length} 份 · 考卷 ${orphanExams.length} 份（可重新整理或刪除）</summary><div class="p-4 border-t border-amber-50 space-y-2">${unassigned.map(adminHubMaterialRow).join('')}${orphanExams.map(q=>`<div class="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs"><b>📝 ${escapeHtml(q.title)}</b> · ${escapeHtml(examDrawLabel(q))} · 及格 ${Number(q.passingScore||80)} 分</div>`).join('')}</div></details>`:''}</div></div>`;
      if(courses.length>visibleCourses.length){
          const more=document.createElement('button');
          more.type='button';
          more.className='mt-3 rounded-xl border border-violet-200 bg-white px-4 py-2 text-xs font-bold text-violet-800';
          more.textContent=`顯示更多課程（已顯示 ${visibleCourses.length}／${courses.length}）`;
          more.addEventListener('click',()=>{
              box.dataset.courseVisibleLimit=String(visibleLimit+30);
              paintAdminCourseMaterialHub(box,box._learningAssignmentState||state);
          });
          box.querySelector('.admin-course-list')?.appendChild(more);
      }
      appendCourseFeedbackSummaryPanels(box,visibleCourses);
      box.dataset.ready='1';
      bindLearningAssignmentControls(box,state);
      // Consumers that decorate each card can settle synchronously after the
      // complete replacement above, rather than racing a later observer turn.
      box.dispatchEvent(new CustomEvent('teacher-course-surface-rendered-1014',{bubbles:true}));
  }

  async function renderAdminCourseMaterialHub(force=false){
      const box=document.getElementById('admin-course-material-hub');
      if(!box)return;
      const area=document.getElementById('wizard-area')?.value||currentTrainingArea;
      const group=document.getElementById('wizard-group')?.value||currentGroupKey;
      const key=adminScopeKey(area,group);
      if(box.dataset.courseScope!==key){
          box.dataset.courseScope=key;
          box.dataset.courseVisibleLimit='30';
      }
      if(box.dataset.courseRefreshActive==='1'&&box.dataset.courseRefreshScope===key&&box._adminCourseMaterialRefresh){
          const activeWasForced=box.dataset.courseRefreshForce==='1';
          if(!force&&activeWasForced){
              // Let one cached/background render take ownership while the
              // forced request is still fetching. Its cached course list keeps
              // the surface stable; the forced material result reconciles in
              // after the current owner settles.
          }else if(force&&!activeWasForced){
              // A forced refresh arriving behind a cached/background refresh
              // waits for that owner, then becomes the single fresh owner.
              try{await box._adminCourseMaterialRefresh;}catch(_error){}
              if(box.dataset.courseScope===key)return renderAdminCourseMaterialHub(true);
          }else{
              return box._adminCourseMaterialState||null;
          }
      }
      const generation=String((Number(box.dataset.courseRenderGeneration)||0)+1);
      box.dataset.courseRefreshActive='1';
      box.dataset.courseRefreshScope=key;
      box.dataset.courseRefreshForce=force?'1':'0';
      box.dataset.courseRefreshOwnerGeneration=generation;
      box.dataset.courseRenderGeneration=generation;
      const paintCurrent=()=>{
          if(box.dataset.courseRenderGeneration===generation && box.dataset.courseScope===key) paintAdminCourseMaterialHub(box,state);
      };
      const courseCache=adminCoursesCache.get(key);
      const materialCache=Array.isArray(adminMaterialsCache.data)?adminMaterialsCache.data:[];
      const state={
          area,group,
          courses:Array.isArray(courseCache?.data)?courseCache.data:[],
          materials:materialCache,
          cats:[],
          assignments:[],
          assignmentAccess:null,
          loading:{
              courses:!(Array.isArray(courseCache?.data)&&!force&&(Date.now()-courseCache.at)<ADMIN_COURSE_CACHE_MS),
              materials:!(Array.isArray(adminMaterialsCache.data)&&!force&&(Date.now()-adminMaterialsCache.at)<ADMIN_CACHE_MS),
              cats:true,
              assignments:true
          },
          errors:{courses:'',materials:'',cats:'',assignments:''}
      };
      box._adminCourseMaterialState=state;
      paintCurrent();
      const jobs=[];

      if(state.loading.courses){
          jobs.push(fetch(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{})
              .then(async res=>{
                  const data=await res.json().catch(()=>[]);
                  if(!res.ok)throw new Error(data.error||'讀取課程失敗');
                  // A slower render must never overwrite the shared cache after
                  // a newer render has taken ownership of this scope.
                  if(box.dataset.courseRenderGeneration!==generation||box.dataset.courseScope!==key)return;
                  state.courses=Array.isArray(data)?data:[];
                  adminCoursesCache.set(key,{data:state.courses,at:Date.now()});
              })
              .catch(error=>{if(box.dataset.courseRenderGeneration===generation&&box.dataset.courseScope===key)state.errors.courses=error.message||'讀取失敗';})
              .finally(()=>{state.loading.courses=false;paintCurrent();}));
      }

      if(state.loading.materials){
          jobs.push(Promise.resolve(fetchAdminMaterials(force))
              .then(data=>{if(Array.isArray(data))state.materials=data;else if(data==null)throw new Error('教材清單未回傳資料');})
              .catch(error=>{state.errors.materials=error.message||'讀取失敗';})
              .finally(()=>{state.loading.materials=false;paintCurrent();}));
      }

      jobs.push(fetch(`/api/quiz-categories?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{credentials:'same-origin',cache:'no-store'})
          .then(async res=>{const data=await res.json().catch(()=>[]);if(!res.ok)throw new Error(data.error||'讀取考卷失敗');state.cats=Array.isArray(data)?data:[];})
          .catch(error=>{state.errors.cats=error.message||'讀取失敗';})
          .finally(()=>{state.loading.cats=false;paintCurrent();}));

      jobs.push(fetch(`/api/learning-assignments?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{credentials:'same-origin',cache:'no-store'})
          .then(async res=>{
              const data=await res.json().catch(()=>[]);
              if(res.status===403){state.assignmentAccess=false;state.assignments=[];return;}
              if(!res.ok)throw new Error(data.error||'讀取課程指派失敗');
              state.assignmentAccess=true;
              state.assignments=Array.isArray(data)?data:[];
          })
          .catch(error=>{state.assignmentAccess=false;state.errors.assignments=error.message||'讀取失敗';})
          .finally(()=>{state.loading.assignments=false;paintCurrent();}));

      // Presentation refresh is deliberately nonblocking. Keep a handle for
      // diagnostics without forcing every caller to wait for a slow provider.
      // Multiple workspace modules can request a refresh at nearly the same time.
      // If this generation finishes after a newer render has taken ownership,
      // reconcile once more from the now-fresh shared caches instead of silently
      // discarding the completed material/course data and leaving a stale 0/0 card.
      const refreshPromise=Promise.allSettled(jobs).then(results=>{
          paintCurrent();
          if(box.dataset.courseScope===key && box.dataset.courseRenderGeneration!==generation){
              if(box.dataset.courseReconcileScheduled!=='1'){
                  box.dataset.courseReconcileScheduled='1';
                  const currentOwner=box._adminCourseMaterialRefresh;
                  Promise.resolve(currentOwner).catch(()=>{}).finally(()=>{
                      delete box.dataset.courseReconcileScheduled;
                      if(box.dataset.courseScope===key) void renderAdminCourseMaterialHub(false);
                  });
              }
          }
          return results;
      }).finally(()=>{
          if(box.dataset.courseRefreshOwnerGeneration===generation){
              delete box.dataset.courseRefreshActive;
              delete box.dataset.courseRefreshForce;
              delete box.dataset.courseRefreshOwnerGeneration;
          }
      });
      box._adminCourseMaterialRefresh=refreshPromise;
      return state;
  }

  window.jumpToAdminQuiz=jumpToAdminQuiz;
  window.adminMaterialTypeBadge=adminMaterialTypeBadge;
  window.adminHubMaterialRow=adminHubMaterialRow;
  window.paintAdminCourseMaterialHub=paintAdminCourseMaterialHub;
  window.renderAdminCourseMaterialHub=renderAdminCourseMaterialHub;
})();
