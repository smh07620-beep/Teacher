/* V5.9.0 · 後台內容、題庫、帳號與系統管理 */
let currentReviewRecordIndex=null;
function openEssayReview(index){
    const r=adminRecords[index]; if(!r) return; currentReviewRecordIndex=index;
    const essays=(r.answersDetail||[]).map((a,i)=>({a,i})).filter(x=>x.a.questionType==='essay');
    if(!essays.length){alert('此考卷沒有問答題。');return;}
    document.getElementById('essay-review-panel').classList.remove('hidden');
    document.getElementById('essay-review-meta').textContent=`${r.name}｜${r.empId}｜${r.quizTitle}｜目前：${r.reviewStatus==='pending'?'待批改':`${r.score} 分`}`;
    document.getElementById('essay-reviewer-name').value=r.reviewerName||r.evaluatorName||readLocalMemory(EVALUATOR_NAME_MEMORY_KEY)||'';
    document.getElementById('essay-review-comment').value=r.reviewComment||'';
    document.getElementById('essay-review-questions').innerHTML=essays.map(({a,i})=>`<div class="bg-white border border-rose-100 rounded-xl p-3 space-y-2"><div class="font-semibold text-sm text-slate-800">第 ${i+1} 題：${escapeHtml(a.questionText||'')}</div><div class="text-sm bg-slate-50 rounded-lg p-3 whitespace-pre-wrap">${escapeHtml(a.userAnswer||'未答')}</div><div class="grid grid-cols-1 md:grid-cols-4 gap-2 items-center"><label class="text-xs font-bold text-slate-600">本題分數 0–100</label><input id="essay-score-${i}" type="number" min="0" max="100" step="1" value="${a.reviewScore ?? ''}" class="px-2 py-1.5 border rounded-lg text-sm"><input id="essay-comment-${i}" type="text" value="${escapeHtml(a.reviewComment||'')}" placeholder="本題評語（選填）" class="md:col-span-2 px-2 py-1.5 border rounded-lg text-sm"></div>${a.reviewerName?`<div class="text-[11px] text-slate-500">上次批改者：${escapeHtml(a.reviewerName)}${a.reviewedAt?'・'+escapeHtml(a.reviewedAt):''}</div>`:''}</div>`).join('');
    document.getElementById('essay-review-panel').scrollIntoView({behavior:'smooth'});
}
function closeEssayReview(){document.getElementById('essay-review-panel').classList.add('hidden'); currentReviewRecordIndex=null;}
async function submitEssayReview(){
    if(currentReviewRecordIndex===null) return; const r=adminRecords[currentReviewRecordIndex]; const key=await getAdminKey(); if(!key)return;
    const reviewerName=document.getElementById('essay-reviewer-name').value.trim(); if(!reviewerName){alert('請填寫批改者姓名；每一題問答題都會保存此批改者。');return;}
    const essayScores={},essayComments={}; let missing=[]; (r.answersDetail||[]).forEach((a,i)=>{if(a.questionType==='essay'){const v=document.getElementById(`essay-score-${i}`).value;if(v==='')missing.push(i+1);essayScores[i]=v;essayComments[i]=document.getElementById(`essay-comment-${i}`).value;}}); if(missing.length){alert(`問答題必須逐題給分。尚未評分：第 ${missing.join('、')} 題`);return;}
    const res=await fetch(`/api/records/${encodeURIComponent(r.id)}/review`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({essayScores,essayComments,reviewerName,reviewComment:document.getElementById('essay-review-comment').value})});
    const data=await res.json().catch(()=>({})); if(!res.ok){alert(data.error||'批改儲存失敗');return;} alert(`批改完成，最終成績 ${data.score} 分（${data.status}）`); closeEssayReview(); await renderAdminTable();
}

function adminCourseRowHTML(c, optimistic=false){
    return `<div data-course-id="${escapeHtml(c.id||'')}" class="flex justify-between items-center bg-white border ${optimistic?'border-violet-300 ring-2 ring-violet-100':'border-violet-100'} rounded-lg px-3 py-2 transition-all"><div><div class="text-sm font-semibold flex items-center gap-2">${escapeHtml(c.title||'')}${optimistic?'<span class="text-[10px] px-2 py-0.5 rounded-full bg-violet-50 text-violet-700">剛建立</span>':''}</div><div class="text-xs text-slate-400">${escapeHtml(c.desc||'')}</div></div><button onclick="adminDeleteCourse('${c.id}')" class="text-xs text-rose-600">刪除</button></div>`;
}
function paintAdminCourses(list, optimisticId=''){
    const box=document.getElementById('admin-courses-list'); if(!box)return;
    box.innerHTML=list.length?'<div class="text-xs font-bold text-violet-800">既有課程</div>'+list.map(c=>adminCourseRowHTML(c,c.id===optimisticId)).join(''):'<div class="text-xs text-slate-400">目前無課程</div>';
}
function optimisticInsertAdminCourse(course, area, group){
    const k=adminScopeKey(area,group); const old=adminCoursesCache.get(k)?.data||[];
    const list=[course,...old.filter(c=>c.id!==course.id)]; adminCoursesCache.set(k,{data:list,at:Date.now()});
    const currentArea=document.getElementById('wizard-area')?.value||'pgy', currentGroup=document.getElementById('wizard-group')?.value||'grpBio';
    if(currentArea===area&&currentGroup===group) paintAdminCourses(list,course.id);
}
async function renderAdminCourses(force=false){
    const key=await getAdminKey(); if(!key)return; const box=document.getElementById('admin-courses-list'); if(!box)return;
    const area=document.getElementById('wizard-area')?.value||'pgy', group=document.getElementById('wizard-group')?.value||'grpBio';
    const k=adminScopeKey(area,group), cached=adminCoursesCache.get(k), now=Date.now();
    if(cached?.data) paintAdminCourses(cached.data);
    if(!force && cached?.data && (now-cached.at)<ADMIN_COURSE_CACHE_MS){ refreshAdminMaterialCourses(); return; }
    if(!cached?.data) box.innerHTML='<div class="text-xs text-slate-400 animate-pulse">讀取課程中…</div>'; else box.classList.add('opacity-70');
    try{
        const res=await fetch(`/api/courses/admin?area=${area}&group=${group}`,{headers:{'X-Admin-Key':key}}); const cs=await res.json().catch(()=>[]);
        if(!res.ok) throw new Error(cs.error||'讀取課程失敗');
        adminCoursesCache.set(k,{data:Array.isArray(cs)?cs:[],at:Date.now()}); paintAdminCourses(Array.isArray(cs)?cs:[]);
    }catch(e){ if(!cached?.data) box.innerHTML=`<div class="text-xs text-rose-500">❌ ${escapeHtml(e.message)}</div>`; }
    finally{ box.classList.remove('opacity-70'); refreshAdminMaterialCourses(); }
}
async function refreshAdminMaterialCourses(){
    const sel=document.getElementById('admin-material-course'); if(!sel)return; const area=document.getElementById('admin-material-area')?.value||currentTrainingArea, group=document.getElementById('admin-material-group')?.value||currentGroupKey;
    const res=await fetch(`/api/courses?area=${area}&group=${group}`); const cs=res.ok?await res.json():[]; sel.innerHTML='<option value="">未指定課程</option>'+cs.map(c=>`<option value="${c.id}">${escapeHtml(c.title)}</option>`).join('');
}
async function adminDeleteCourse(id){if(!confirm('刪除課程？教材與考卷不會刪除，只會解除課程關聯。'))return; const key=await getAdminKey(); if(!key)return; const r=await fetch(`/api/courses/${id}`,{method:'DELETE',headers:{'X-Admin-Key':key}}); if(!r.ok){alert('刪除失敗');return;} await renderAdminCourses(true); await renderAdminCourseMaterialHub(true);}

function adminMaterialTypeBadge(m){
    const meta={standard:['📚','教材'],video:['🎬','影音'],atlas:['🔬','Atlas'],infographic:['📊','圖表'],troubleshooting:['🧰','錯誤分析'],case:['🩸','案例'],sop:['📑','SOP']}[m.materialType]||['📄','教材'];
    return `${meta[0]} ${meta[1]}`;
}
function adminHubMaterialRow(m){
    return `<div class="flex flex-col lg:flex-row lg:items-center justify-between gap-2 rounded-xl bg-slate-50 border border-slate-100 px-3 py-2.5"><div class="min-w-0"><div class="text-xs font-bold text-slate-800 truncate">${escapeHtml(m.title||m.filename||'未命名教材')}</div><div class="text-[10px] text-slate-500 mt-1">${adminMaterialTypeBadge(m)}${m.categoryLabel?' · 對應：'+escapeHtml(m.categoryLabel):''}${m.active===false?' · 已停用':''}</div></div>${m.isBuiltin?'':`<div class="flex gap-1.5 shrink-0"><button onclick="editAdminMaterial('${m.id}')" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-indigo-600 text-white">編輯</button><button onclick="toggleAdminMaterial('${m.id}',${m.active?'false':'true'})" class="text-[10px] px-2.5 py-1.5 rounded-lg bg-amber-500 text-white">${m.active?'停用':'啟用'}</button></div>`}</div>`;
}
async function renderAdminCourseMaterialHub(force=false){
    const box=document.getElementById('admin-course-material-hub');if(!box)return;const area=document.getElementById('wizard-area')?.value||currentTrainingArea,group=document.getElementById('wizard-group')?.value||currentGroupKey;if(!box.dataset.ready)box.innerHTML='<div class="text-xs text-slate-400 animate-pulse">整理課程、教材、題庫與考卷關聯中…</div>';
    const adminKey=await getAdminKey();if(!adminKey)return;
    try{const [courseRes,materials,catRes]=await Promise.all([fetch(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{headers:{"X-Admin-Key":adminKey}}),fetchAdminMaterials(force),fetch(`/api/quiz-categories?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`)]);const courses=courseRes.ok?await courseRes.json():[],cats=catRes.ok?await catRes.json():[],scoped=(materials||[]).filter(m=>(m.area||'internal')===area&&(m.group||'grpBio')===group),cards=[];
        for(const c of courses){const mats=teachingOrderedMaterials(c,scoped.filter(m=>m.courseId===c.id)),exams=(cats||[]).filter(q=>q.courseId===c.id),qcount=exams.reduce((n,q)=>n+examBankCount(q),0);cards.push(`<details class="group rounded-2xl border border-violet-100 bg-white overflow-hidden" ${c.id===box.dataset.lastCreated?'open':''}><summary class="cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3 hover:bg-violet-50/50 transition-colors"><div class="min-w-0"><div class="font-black text-sm text-slate-900 truncate">📘 ${escapeHtml(c.title||'未命名課程')}</div>${c.desc&&c.desc.trim()!==c.title?.trim()?`<div class="text-[11px] text-slate-500 mt-1">${escapeHtml(c.desc)}</div>`:''}<div class="flex flex-wrap gap-1.5 mt-2"><span class="course-stat-chip">📚 教材 ${mats.length} 份</span><span class="course-stat-chip">📝 題庫 ${qcount} 題</span><span class="course-stat-chip">📋 考卷 ${exams.length} 份</span></div></div><div class="flex items-center gap-2 shrink-0"><span class="course-stat-chip">${c.active?"已啟用":"已停用"}</span><button onclick="event.preventDefault();event.stopPropagation();teachingEditCourse('${c.id}')" class="teaching-primary">編排課程</button><button onclick="event.preventDefault();event.stopPropagation();adminDeleteCourse('${c.id}')" class="text-[10px] text-rose-600 px-2 py-1">刪除課程</button></div></summary><div class="border-t border-violet-50 p-4 grid lg:grid-cols-2 gap-4"><div><div class="text-xs font-black text-slate-700 mb-2">📚 教材</div><div class="space-y-2">${mats.length?mats.map(adminHubMaterialRow).join(''):'<div class="text-xs text-slate-400">尚未關聯教材</div>'}</div></div><div><div class="text-xs font-black text-slate-700 mb-2">📋 考卷與出題設定</div><div class="space-y-2">${exams.length?exams.map(q=>`<div class="rounded-xl bg-indigo-50/60 border border-indigo-100 px-3 py-2.5"><div class="flex items-start justify-between gap-2"><div><div class="text-xs font-bold text-indigo-950">${escapeHtml(q.title||'未命名考卷')}</div><div class="flex flex-wrap gap-1.5 mt-1.5"><span class="text-[10px] text-indigo-700">👤 ${escapeHtml(examAudienceLabel(q))}</span><span class="text-[10px] text-indigo-700">🧠 題庫 ${examBankCount(q)} 題</span><span class="text-[10px] text-indigo-700">📋 ${escapeHtml(examDrawLabel(q))}</span><span class="text-[10px] text-indigo-700">🎯 ${Number(q.passingScore||80)} 分</span>${q.blindMode?'<span class="text-[10px] text-slate-700">🕶️ 盲測</span>':''}</div></div><button onclick="jumpToAdminQuiz('${q.id}','${area}','${group}')" class="text-[10px] bg-indigo-700 text-white rounded-lg px-2.5 py-1.5 shrink-0">管理題庫</button></div></div>`).join(''):'<div class="text-xs text-slate-400">尚未建立考卷</div>'}</div></div></div></details>`);}
        const unassigned=scoped.filter(m=>!m.courseId),orphanExams=(cats||[]).filter(q=>!q.courseId);box.innerHTML=`<div class="rounded-2xl border border-violet-200 bg-violet-50/40 p-4"><div class="flex items-center justify-between gap-3"><div><h5 class="font-black text-violet-950">🗂️ 課程 → 教材 → 題庫 → 考卷</h5><p class="text-[11px] text-violet-700 mt-1">每門課程直接顯示教材數、題庫總題數、考卷份數與出題規則。</p></div><button onclick="renderAdminCourseMaterialHub(true)" class="text-[10px] px-3 py-1.5 rounded-lg bg-white border border-violet-200 text-violet-700">↻ 更新</button></div><div class="mt-3 space-y-2">${cards.join('')||'<div class="text-xs text-slate-400 py-3">目前尚無課程。</div>'}${(unassigned.length||orphanExams.length)?`<details class="rounded-2xl border border-amber-100 bg-white overflow-hidden"><summary class="cursor-pointer list-none px-4 py-3 font-bold text-xs text-amber-800">📁 通用／未歸類：教材 ${unassigned.length} 份 · 考卷 ${orphanExams.length} 份</summary><div class="p-4 border-t border-amber-50 space-y-2">${unassigned.map(adminHubMaterialRow).join('')}${orphanExams.map(q=>`<div class="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs"><b>📝 ${escapeHtml(q.title)}</b> · ${escapeHtml(examDrawLabel(q))} · 及格 ${Number(q.passingScore||80)} 分</div>`).join('')}</div></details>`:''}</div></div>`;box.dataset.ready='1';
    }catch(e){box.innerHTML=`<div class="text-xs text-rose-500">❌ 無法整理課程總覽：${escapeHtml(e.message)}</div>`;}
}

async function jumpToAdminQuiz(catId,area,group){
    await switchAdminSection('quiz',true);const a=document.getElementById('admin-quiz-area'),g=document.getElementById('admin-quiz-group');if(a)a.value=area;if(g){g.innerHTML=groupOptionsForArea(area);g.value=group;}await renderAdminQuizCategories(true);setTimeout(()=>{const btn=[...document.querySelectorAll('button')].find(b=>b.getAttribute('onclick')?.includes(`'${catId}'`)&&b.textContent.includes('題庫'));btn?.scrollIntoView({behavior:'smooth',block:'center'});},100);
}
let courseWizardBusy=false;
const sleepMs=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
function setCourseWizardProgress(percent,label,note=''){
    const pct=Math.max(0,Math.min(100,Math.round(Number(percent)||0)));
    const wrap=document.getElementById('wizard-progress-wrap'), bar=document.getElementById('wizard-progress-bar'), barWrap=document.getElementById('wizard-progress-bar-wrap');
    const pctEl=document.getElementById('wizard-progress-percent'), labelEl=document.getElementById('wizard-progress-label'), noteEl=document.getElementById('wizard-progress-note');
    wrap?.classList.remove('hidden');
    if(bar) bar.style.width=`${pct}%`;
    if(barWrap) barWrap.setAttribute('aria-valuenow',String(pct));
    if(pctEl) pctEl.textContent=`${pct}%`;
    if(labelEl) labelEl.textContent=label||'處理中…';
    if(noteEl && note) noteEl.textContent=note;
    if(pct>=100 && bar) bar.className='h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-[width] duration-500 ease-out';
    else if(bar) bar.className='h-full rounded-full bg-gradient-to-r from-violet-600 to-fuchsia-500 transition-[width] duration-500 ease-out';
}
function setCourseWizardDetail(text=''){
    const el=document.getElementById('wizard-progress-detail');
    if(!el)return;
    if(text){el.textContent=text;el.classList.remove('hidden');}else{el.textContent='';el.classList.add('hidden');}
}
async function pollWizardUploadProgress(progressId, fileIndex, fileCount, fileName, key, stopSignal){
    let last=-1;
    while(!stopSignal.done){
        try{
            const res=await fetch(`/api/slides/upload-progress/${encodeURIComponent(progressId)}`,{headers:{'X-Admin-Key':key},cache:'no-store'});
            if(res.ok){
                const d=await res.json();
                const sub=Math.max(0,Math.min(100,Number(d.percent||0)));
                const base=45+((fileIndex-1)/Math.max(1,fileCount))*40;
                const span=40/Math.max(1,fileCount);
                const overall=base+(sub/100)*span;
                if(sub!==last || d.detail){
                    setCourseWizardProgress(overall,`${fileIndex}/${fileCount} ${d.stage||'處理教材'}`,`STEP 3 / 4：${fileName}`);
                    const counter=(Number(d.total||0)>0)?` · ${Number(d.current||0)}/${Number(d.total||0)}`:'';
                    setCourseWizardDetail(`${d.detail||'處理中…'}${counter}`);
                    last=sub;
                }
            }
        }catch(_e){}
        await sleepMs(550);
    }
}
async function waitWizardMaterialJob(jobId,fileIndex,fileCount,fileName,key){
    const base=45+((fileIndex-1)/Math.max(1,fileCount))*40;
    const span=40/Math.max(1,fileCount);
    const deadline=Date.now()+45*60*1000;
    while(Date.now()<deadline){
        const res=await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`,{headers:{'X-Admin-Key':key},cache:'no-store'});
        const job=await res.json().catch(()=>({}));
        if(!res.ok)throw new Error(job.error||`${fileName} 背景工作狀態讀取失敗`);
        const sub=Math.max(0,Math.min(100,Number(job.progress||0)));
        setCourseWizardProgress(base+(sub/100)*span,`${fileIndex}/${fileCount} ${job.stage||'背景處理教材'}`,`STEP 3 / 4：${fileName}`);
        setCourseWizardDetail(`${job.detail||'背景處理中…'}${job.attempts?` · 第 ${job.attempts}/${job.maxAttempts||3} 次`:''}`);
        if(job.status==='completed') return job.result||{id:job.materialId};
        if(job.status==='failed') throw new Error(job.error||job.detail||`${fileName} 背景處理失敗`);
        if(job.status==='cancelled') throw new Error(`${fileName} 背景工作已取消`);
        await sleepMs(700);
    }
    throw new Error(`${fileName} 背景處理等待超過 45 分鐘；工作仍可能在後台執行，請到背景工作中心查看。`);
}
function uploadWizardMaterial(fd, progressId, fileIndex, fileCount, fileName, key){
    return new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();
        const base=45+((fileIndex-1)/Math.max(1,fileCount))*40;
        const span=40/Math.max(1,fileCount);
        xhr.open('POST','/api/material-jobs/upload',true);
        xhr.setRequestHeader('X-Admin-Key',key);
        xhr.upload.onprogress=(ev)=>{
            if(!ev.lengthComputable)return;
            const sent=Math.max(0,Math.min(1,ev.loaded/ev.total));
            const overall=base+sent*(span*0.10);
            setCourseWizardProgress(overall,`${fileIndex}/${fileCount} 接收大型教材`,`STEP 3 / 4：${fileName}`);
            setCourseWizardDetail(`瀏覽器 → Render ${(sent*100).toFixed(0)}% · ${(ev.loaded/1024/1024).toFixed(1)} / ${(ev.total/1024/1024).toFixed(1)} MB`);
        };
        xhr.onload=async()=>{
            let data={}; try{data=JSON.parse(xhr.responseText||'{}');}catch(_e){}
            if(xhr.status<200||xhr.status>=300){reject(new Error(data.error||`${fileName} 加入背景佇列失敗 (HTTP ${xhr.status})`));return;}
            try{
                setCourseWizardDetail(`✅ 教材已安全接收並加入背景佇列 ${data.jobId||''}；轉檔不佔用 Web worker。`);
                const result=await waitWizardMaterialJob(data.jobId,fileIndex,fileCount,fileName,key);
                resolve(result);
            }catch(err){reject(err);}
        };
        xhr.onerror=()=>reject(new Error(`${fileName} 網路上傳失敗`));
        xhr.ontimeout=()=>reject(new Error(`${fileName} 傳送到伺服器逾時`));
        xhr.timeout=20*60*1000;
        xhr.send(fd);
    });
}
const WIZARD_MATERIAL_TYPE_META={
    auto:{label:'✨ 自動依教材判斷',icon:'✨'},standard:{label:'核心課程教材',icon:'📚'},video:{label:'操作教學影片 / 影音',icon:'🎬'},atlas:{label:'Atlas / 數位顯微鏡圖庫',icon:'🔬'},infographic:{label:'資訊圖表 / 流程圖',icon:'📊'},troubleshooting:{label:'常見錯誤分析 / Troubleshooting',icon:'🧰'},case:{label:'案例分析',icon:'🩸'},sop:{label:'SOP 站內閱讀',icon:'📑'}
};
let wizardMaterialTypes=[];
let wizardMaterialTitles=[];
function suggestWizardMaterialType(file){
    const name=(file?.name||'').toLowerCase(); const ext=(name.match(/\.([^.]+)$/)||[])[1]||'';
    const has=(arr)=>arr.some(k=>name.includes(k));
    if(['mp4','webm','mov','m4v','mp3','wav','m4a','ogg','srt','vtt'].includes(ext)) return 'video';
    if(has(['sop','標準作業','作業標準','作業程序','規範','指引'])) return 'sop';
    if(has(['故障','異常','troubleshooting','排除','溶血','量不足','westgard','qc違反','qc 異常'])) return 'troubleshooting';
    if(has(['案例','輸血反應','discrepancy','case'])) return 'case';
    if(has(['流程圖','流程','infographic','資訊圖表','管制圖','westgard rules'])) return 'infographic';
    if(has(['atlas','圖譜','顯微鏡','血球型態','結晶','寄生蟲','蟲卵','原蟲','細菌形態','真菌形態'])) return 'atlas';
    if(['jpg','jpeg','png','webp','gif'].includes(ext) && has(['細胞','血球','菌','結晶','蟲','沉渣','抹片'])) return 'atlas';
    return 'auto';
}
function wizardMaterialTypeOptions(selected){
    return Object.entries(WIZARD_MATERIAL_TYPE_META).map(([v,m])=>`<option value="${v}" ${selected===v?'selected':''}>${m.icon} ${m.label}</option>`).join('');
}
function renderWizardMaterialClassifier(reSuggest=false){
    const input=document.getElementById('wizard-material-files'), wrap=document.getElementById('wizard-material-classifier'), list=document.getElementById('wizard-material-classifier-list');
    if(!input||!wrap||!list)return; const files=[...(input.files||[])];
    if(!files.length){wizardMaterialTypes=[];wizardMaterialTitles=[];wrap.classList.add('hidden');list.innerHTML='';return;}
    if(reSuggest || wizardMaterialTypes.length!==files.length) wizardMaterialTypes=files.map(suggestWizardMaterialType);
    if(wizardMaterialTitles.length!==files.length) wizardMaterialTitles=files.map(f=>(f.name||'').replace(/\.[^.]+$/,''));
    wrap.classList.remove('hidden');
    list.innerHTML=files.map((f,i)=>{const suggested=suggestWizardMaterialType(f), current=wizardMaterialTypes[i]||suggested; const meta=WIZARD_MATERIAL_TYPE_META[suggested]||WIZARD_MATERIAL_TYPE_META.auto;return `<div class="grid xl:grid-cols-[1fr_1fr_290px] gap-3 items-center rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-3"><div class="min-w-0"><div class="flex items-center gap-2"><span class="text-lg">${meta.icon}</span><p class="text-xs font-bold text-slate-800 truncate">${escapeHtml(f.name)}</p></div><p class="mt-1 text-[10px] text-slate-400">${(f.size/1024/1024).toFixed(1)} MB · 初步建議：${escapeHtml(meta.label)}</p></div><div><label class="block text-[10px] font-bold text-slate-500 mb-1">教材顯示名稱</label><input data-wizard-material-title-index="${i}" value="${escapeHtml(wizardMaterialTitles[i]||'')}" oninput="wizardMaterialTitles[${i}]=this.value" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white" placeholder="可自訂每份教材名稱"></div><div><label class="block text-[10px] font-bold text-slate-500 mb-1">教材模組</label><select data-wizard-material-index="${i}" onchange="wizardMaterialTypes[${i}]=this.value" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white">${wizardMaterialTypeOptions(current)}</select></div></div>`}).join('');
}
function applyWizardMaterialBulkType(){
    const v=document.getElementById('wizard-material-bulk-type')?.value||''; if(!v)return;
    const files=[...(document.getElementById('wizard-material-files')?.files||[])]; wizardMaterialTypes=files.map(()=>v);
    renderWizardMaterialClassifier(false);
}
function setCourseWizardBusy(busy){
    courseWizardBusy=!!busy;
    const ids=['wizard-area','wizard-group','wizard-course-title','wizard-exam-title','wizard-course-desc','wizard-material-files','wizard-create-btn','wizard-clear-btn','wizard-material-bulk-type'];
    ids.forEach(id=>{ const el=document.getElementById(id); if(el) el.disabled=courseWizardBusy; });
    document.querySelectorAll('[data-wizard-material-index],[data-wizard-material-title-index]').forEach(el=>{el.disabled=courseWizardBusy;});
    const formBox=document.getElementById('wizard-course-title')?.closest('.grid');
    if(formBox) formBox.classList.toggle('opacity-80',courseWizardBusy);
}
function resetCourseWizardForm(clearStatus=false,force=false){
    if(courseWizardBusy && !force){
        const st=document.getElementById('wizard-status');
        if(st) st.textContent='⏳ 建立尚未完成，完成前不可清空表單。';
        return false;
    }
    // 保留目前訓練區與組別，方便管理者連續建立同一組課程；其餘輸入全部清空。
    const title=document.getElementById('wizard-course-title');
    const exam=document.getElementById('wizard-exam-title');
    const desc=document.getElementById('wizard-course-desc');
    const files=document.getElementById('wizard-material-files');
    const st=document.getElementById('wizard-status');
    if(title) title.value='';
    if(exam) exam.value='';
    if(desc) desc.value='';
    if(files) files.value='';
    wizardMaterialTypes=[]; wizardMaterialTitles=[];
    document.getElementById('wizard-material-classifier')?.classList.add('hidden');
    const classifierList=document.getElementById('wizard-material-classifier-list'); if(classifierList) classifierList.innerHTML='';
    if(clearStatus && st) st.textContent='';
    title?.focus();
    return true;
}
async function adminCreateCourseBundle(){
    if(courseWizardBusy) return;
    const key=await getAdminKey(); if(!key)return;
    const btn=document.getElementById('wizard-create-btn'), st=document.getElementById('wizard-status');
    const area=document.getElementById('wizard-area').value, group=document.getElementById('wizard-group').value, title=document.getElementById('wizard-course-title').value.trim(), desc=document.getElementById('wizard-course-desc').value.trim(), examTitle=document.getElementById('wizard-exam-title').value.trim(), files=[...document.getElementById('wizard-material-files').files];
    if(wizardMaterialTypes.length!==files.length) wizardMaterialTypes=files.map(suggestWizardMaterialType);
    if(wizardMaterialTitles.length!==files.length) wizardMaterialTitles=files.map(f=>(f.name||'').replace(/\.[^.]+$/,''));
    if(!title){alert('請輸入課程名稱');return;}
    setCourseWizardBusy(true);
    setCourseWizardProgress(5,'準備建立資料…','建立期間表單已鎖定；完成前不會清空。');
    st.textContent='⏳ 正在建立整套課程，請勿關閉此視窗…';
    let completed=false;
    try{
        setCourseWizardProgress(10,'建立課程…','STEP 1 / 4：建立課程基本資料');
        let res=await fetch('/api/courses',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({area,group,title,desc})});
        let course=await res.json(); if(!res.ok)throw new Error(course.error||'課程建立失敗');
        optimisticInsertAdminCourse(course,area,group);
        setCourseWizardProgress(30,'課程已建立','STEP 1 / 4 完成');

        let categoryId='', createdCat=null;
        if(examTitle){
            setCourseWizardProgress(35,'建立考卷…','STEP 2 / 4：建立並連結課後考卷');
            res=await fetch('/api/quiz-categories',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({area,group,title:examTitle,desc:`${title} 課後評量`,courseId:course.id})});
            const cat=await res.json(); if(!res.ok)throw new Error(cat.error||'考卷建立失敗'); categoryId=cat.id; createdCat={...cat,questionCount:0}; optimisticInsertQuizCategory(createdCat,area,group);
        }
        setCourseWizardProgress(45,examTitle?'考卷已建立':'未設定考卷，繼續教材處理','STEP 2 / 4 完成');

        let n=0; const uploaded=[];
        if(files.length){
            for(const f of files){
                const before=45+(n/files.length)*40;
                setCourseWizardProgress(before,`上傳教材 ${n+1}/${files.length}` ,`STEP 3 / 4：${f.name}`);
                st.textContent=`⏳ 上傳教材 ${n+1}/${files.length}：${f.name}`;
                const progressId=`wiz-${Date.now()}-${Math.random().toString(36).slice(2,9)}-${n}`;
                const chosenType=wizardMaterialTypes[n]||'auto';
                const fd=new FormData(); fd.append('file',f);fd.append('title',(wizardMaterialTitles[n]||f.name.replace(/\.[^.]+$/,'')).trim());fd.append('desc',desc);fd.append('group',group);fd.append('area',area);fd.append('courseId',course.id);fd.append('category',categoryId);fd.append('materialType',chosenType);fd.append('progressId',progressId);
                const dd=await uploadWizardMaterial(fd,progressId,n+1,files.length,f.name,key); uploaded.push(dd); n++;
                if(dd?.materialType){wizardMaterialTypes[n-1]=dd.materialType;}
                setCourseWizardProgress(45+(n/files.length)*40,`教材 ${n}/${files.length} 已完成`,`STEP 3 / 4：已完成 ${n} 份教材`);
                const mt=WIZARD_MATERIAL_TYPE_META[dd?.materialType]||WIZARD_MATERIAL_TYPE_META.standard;
                setCourseWizardDetail(`✅ ${f.name} 已完成處理與雲端儲存 · 分類：${mt.icon} ${mt.label}${dd?.classificationMethod?`（${dd.classificationMethod}）`:''}`);
            }
        }else{
            setCourseWizardProgress(85,'沒有選擇教材，略過上傳','STEP 3 / 4 完成');
        }

        setCourseWizardProgress(90,'同步後台清單…','STEP 4 / 4：更新課程、教材與考卷畫面'); setCourseWizardDetail('正在同步課程、教材、考卷與題庫清單…');
        st.textContent='⏳ 建立內容已完成，正在同步後台清單…';
        invalidateAdminMaterialsCache();
        await Promise.allSettled([renderAdminCourses(true),renderAdminMaterials(true),renderAdminQuizCategories(true),refreshAdminMaterialCategoryOptions()]); await renderAdminCourseMaterialHub(true);
        setCourseWizardProgress(100,'建立完成','所有資料已建立並同步，可開始下一套課程。'); setCourseWizardDetail('✅ 課程、考卷、教材與後台清單已全部同步完成');
        const successMessage=`✅ 已完成「${title}」：教材 ${n} 份${examTitle?'，考卷 1 份':''}`;
        st.textContent=successMessage;
        completed=true;
        // 讓操作者明確看到 100% 完成，再解除鎖定並清空輸入。
        await sleepMs(900);
        setCourseWizardBusy(false);
        resetCourseWizardForm(false,true);
        window.setTimeout(()=>{ if(st.textContent===successMessage) st.textContent=''; },5000);
    }catch(e){
        setCourseWizardProgress(0,'建立未完成',`❌ ${e.message}；表單內容已保留，可確認後重試。`); setCourseWizardDetail(`❌ ${e.message}`);
        st.textContent=`❌ ${e.message}（表單未清空）`;
    }finally{
        if(!completed) setCourseWizardBusy(false);
    }
}


async function getAdminKey() {
    if (adminKey) return adminKey;
    try {
        const auth = await fetch('/api/auth/me', { cache: 'no-store' }).then(r => r.json());
        if (auth.authenticated && auth.user?.role === 'manager') {
            // 後端以登入 session 驗證 manager；保留非空值以相容既有呼叫端。
            adminKey = '__manager_session__';
            return adminKey;
        }
    } catch (_) {}
    const key = prompt('請輸入成績後台管理者金鑰（ADMIN_KEY）：');
    if (!key) return null;
    adminKey = key.trim();
    sessionStorage.setItem('admin_key', adminKey);
    return adminKey;
}

const ADMIN_CACHE_MS = 30000;
const ADMIN_QUIZ_CACHE_MS = 60000;
const ADMIN_COURSE_CACHE_MS = 60000;
let adminMaterialsCache = { data: null, at: 0 };
const adminQuizCategoriesCache = new Map();
const adminCoursesCache = new Map();
const adminSectionLoaded = { content: false, quiz: false, word: false, pgy: false, results: false };
function invalidateAdminMaterialsCache() { adminMaterialsCache = { data: null, at: 0 }; }
function adminScopeKey(area, group){ return `${area || 'internal'}::${group || 'grpBio'}`; }
function setAdminQuizSyncStatus(text, tone='slate'){
    const el=document.getElementById('admin-quiz-sync-status'); if(!el)return;
    const tones={slate:'bg-slate-100 text-slate-500',indigo:'bg-indigo-50 text-indigo-700',emerald:'bg-emerald-50 text-emerald-700',rose:'bg-rose-50 text-rose-700',amber:'bg-amber-50 text-amber-700'};
    el.className=`text-[11px] px-2.5 py-1 rounded-full font-bold ${tones[tone]||tones.slate}`; el.textContent=text;
}
function adminHasExpandedQuestionEditor(box){
    return !!box?.querySelector('[id^="qedit-"]:not(.hidden), textarea[id^="qedit-"]:focus, input[id^="qedit-"]:focus');
}

async function fetchAdminMaterials(force=false) {
    const now = Date.now();
    if (!force && Array.isArray(adminMaterialsCache.data) && (now - adminMaterialsCache.at) < ADMIN_CACHE_MS) {
        return adminMaterialsCache.data;
    }
    const key = await getAdminKey();
    if (!key) return null;
    const res = await fetch('/api/slides/admin', { headers: { 'X-Admin-Key': key } });
    if (res.status === 401) {
        sessionStorage.removeItem('admin_key'); adminKey = '';
        invalidateAdminMaterialsCache();
        alert('管理者金鑰錯誤或尚未設定，請重新輸入。');
        return null;
    }
    const data = await res.json().catch(() => []);
    if (!res.ok) throw new Error(data.error || '無法取得教材清單');
    const list = Array.isArray(data) ? data : [];
    adminMaterialsCache = { data: list, at: Date.now() };
    return list;
}

async function renderStorageStatus(force=false) {
    const box = document.getElementById('admin-storage-status');
    if (!box) return;
    const key = await getAdminKey();
    if (!key) return;
    box.textContent = '讀取檔案儲存狀態中…';
    try {
        const res = await fetch(`/api/storage-status${force?'?refresh=1':''}`, {headers:{'X-Admin-Key':key}});
        const d = await res.json().catch(()=>({}));
        if (!res.ok) throw new Error(d.error || '無法讀取儲存狀態');
        const active = d.activeBackend === 'mega' ? '🟣 MEGA 教材庫' : (d.activeBackend === 'oci' ? '🔴 Oracle（舊）' : (d.activeBackend === 'gdrive' ? '🟢 Google Drive（舊）' : (d.activeBackend === 'r2' ? '☁️ Cloudflare R2（舊）' : (d.activeBackend === 'local' ? '💾 本機儲存' : '❌ 設定錯誤'))));
        const counts = d.materials || {};
        let cloudState='';
        if(d.megaConfigured){
            const sp=d.megaSpace||{};
            const used=sp.usedGb==null?'?':sp.usedGb;
            const total=sp.totalGb==null?'?':sp.totalGb;
            cloudState = `　<span class="text-fuchsia-700">✅ MEGA 已連線・帳號 ${used}/${total} GB・網站硬上限 ${d.megaFreeLimitGb||18} GB${d.megaFreeOnly?'・免費模式':''}</span>`;
        } else if(d.activeBackend==='oci') cloudState='　<span class="text-red-700">Oracle 舊後端仍可讀取</span>';
        else if(d.activeBackend==='gdrive') cloudState=d.gdriveConnected?'　<span class="text-emerald-700">Google Drive 舊後端已連線</span>':'　<span class="text-rose-600">Google Drive 舊後端失效</span>';
        else if(d.activeBackend==='r2') cloudState='　<span class="text-cyan-700">R2 舊後端已啟用</span>';
        else cloudState='　<span class="text-amber-700">⚠️ 請在 Render 設定 MEGA_EMAIL / MEGA_PASSWORD</span>';
        const fallbackState=d.failoverOnFull?(d.fallbackReady?`<div class="text-emerald-700 mt-1">↪ 容量滿載備援：${escapeHtml(d.fallbackBackend||'')} 已就緒</div>`:`<div class="text-amber-700 mt-1">↪ 已要求容量滿載備援，但備援尚未完成設定</div>`):'';
        box.innerHTML = `<b>目前教材儲存：</b>${active}　<span class="text-slate-400">｜</span> MEGA ${counts.mega||0} 份、Oracle ${counts.oci||0} 份、Google Drive ${counts.gdrive||0} 份、R2 ${counts.r2||0} 份、本機 ${counts.local||0} 份` + cloudState + fallbackState +
            (d.error ? `<div class="text-rose-600 mt-1">${escapeHtml(d.error)}</div>` : '');
    } catch (err) { box.innerHTML = `<span class="text-rose-600">❌ ${escapeHtml(err.message)}</span>`; }
}

async function migrateMaterialsToMega() {
    if (!confirm('要將目前仍可讀取的既有教材搬移到 MEGA 嗎？\n\n新檔成功存入 MEGA 後才會更新資料庫；免費模式會在接近網站設定容量上限時停止上傳。')) return;
    const key=await getAdminKey(); if(!key) return;
    const btn=document.getElementById('migrate-mega-btn');
    try {
        if(btn){btn.disabled=true;btn.textContent='⏳ 搬移到 MEGA 中…';}
        const res=await fetch('/api/storage/migrate-to-mega',{method:'POST',headers:{'X-Admin-Key':key}});
        const d=await res.json().catch(()=>({})); if(!res.ok) throw new Error(d.error||'搬移失敗');
        alert(`MEGA 搬移完成：成功 ${d.migrated||0} 份、略過 ${(d.skipped||[]).length} 份、失敗 ${(d.failed||[]).length} 份。`);
        await renderStorageStatus(true); invalidateAdminMaterialsCache(); await renderAdminMaterials(true); await renderAdminCourseMaterialHub(true); await renderSlidesGrid();
    } catch(e){alert('搬移失敗：'+e.message);} finally { if(btn){btn.disabled=false;btn.textContent='☁️ 搬移既有教材到 MEGA';} }
}

async function migrateMaterialsToGoogleDrive() {
    if (!confirm('要將目前尚未存於 Google Drive 的教材搬移到 Google Drive 嗎？\n\n可搬移仍存在 Render 本機的教材；若教材目前在 R2 且 R2 金鑰仍有效，也會先讀出再搬到 Google Drive。搬移成功後舊雲端/本機副本會移除，資料庫與課程/成績資料不會刪除。')) return;
    const key = await getAdminKey();
    if (!key) return;
    const btn = document.getElementById('migrate-gdrive-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 搬移到 Google Drive 中…'; }
    try {
        const res = await fetch('/api/storage/migrate-to-gdrive', {method:'POST', headers:{'X-Admin-Key':key}});
        const d = await res.json().catch(()=>({}));
        if (!res.ok) throw new Error(d.error || '搬移失敗');
        const skipped = Array.isArray(d.skipped) ? d.skipped.length : 0;
        const failed = Array.isArray(d.failed) ? d.failed.length : 0;
        let msg = `Google Drive 搬移完成：成功 ${d.migrated||0} 份、略過 ${skipped} 份、失敗 ${failed} 份。`;
        if (skipped) msg += '\n略過通常表示 Render 本機舊檔已不存在。';
        if (failed && d.failed?.[0]?.reason) msg += `\n第一筆錯誤：${d.failed[0].reason}`;
        alert(msg);
        await renderStorageStatus(true);
        invalidateAdminMaterialsCache(); await renderAdminMaterials(true); await renderAdminCourseMaterialHub(true);
        await renderSlidesGrid();
    } catch (err) { alert(`❌ ${err.message}`); }
    finally { if (btn) { btn.disabled = false; btn.textContent = '🟢 搬移既有教材到 Google Drive'; } }
}

async function migrateLocalMaterialsToR2() {
    if (!confirm('要將目前仍存於本機、而且伺服器上仍存在原始檔的教材搬移到 Cloudflare R2 嗎？\n\n搬移成功後，本機教材檔會刪除；資料庫與課程/成績資料不會刪除。')) return;
    const key = await getAdminKey();
    if (!key) return;
    const btn = document.getElementById('migrate-r2-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 搬移中…'; }
    try {
        const res = await fetch('/api/storage/migrate-to-r2', {method:'POST', headers:{'X-Admin-Key':key}});
        const d = await res.json().catch(()=>({}));
        if (!res.ok) throw new Error(d.error || '搬移失敗');
        const skipped = Array.isArray(d.skipped) ? d.skipped.length : 0;
        const failed = Array.isArray(d.failed) ? d.failed.length : 0;
        alert(`R2 搬移完成：成功 ${d.migrated||0} 份、略過 ${skipped} 份、失敗 ${failed} 份。` + (skipped ? '\n略過通常表示 Render 本機檔案已不存在。' : ''));
        await renderStorageStatus(true);
        invalidateAdminMaterialsCache(); await renderAdminMaterials(true); await renderAdminCourseMaterialHub(true);
        await renderSlidesGrid();
    } catch (err) { alert(`❌ ${err.message}`); }
    finally { if (btn) { btn.disabled = false; btn.textContent = '☁️ 搬移本機教材到 R2（備援）'; } }
}

async function renderAdminMaterials(force=false) {
    const box = document.getElementById('admin-materials-list');
    if (!box) return;
    box.innerHTML = '<p class="text-xs text-slate-400">讀取教材中…</p>';
    try {
        const materials = await fetchAdminMaterials(force);
        if (!materials) return;
        box.innerHTML = materials.map(m => `
            <div class="border border-slate-200 rounded-xl p-3 ${m.isBuiltin ? 'bg-slate-50' : 'bg-white'}">
                <div class="flex flex-col lg:flex-row gap-3 lg:items-center justify-between">
                    <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="font-bold text-sm text-slate-800 break-all">${escapeHtml(m.title || m.filename)}</span>
                            <span class="text-[11px] px-2 py-0.5 rounded-full bg-teal-100 text-teal-700">${escapeHtml((GROUPS[m.group] || GROUPS.grpBio).label)}</span>
                            <span class="text-[11px] px-2 py-0.5 rounded-full ${m.isBuiltin ? 'bg-slate-200 text-slate-600' : 'bg-indigo-100 text-indigo-700'}">${m.isBuiltin ? '內建' : '上傳'}</span>
                            ${!m.isBuiltin ? `<span class="text-[11px] px-2 py-0.5 rounded-full ${m.storageBackend==='mega'?'bg-fuchsia-100 text-fuchsia-800':(m.storageBackend==='oci'?'bg-red-100 text-red-800':(m.storageBackend==='gdrive'?'bg-emerald-100 text-emerald-800':(m.storageBackend==='r2'?'bg-cyan-100 text-cyan-800':'bg-orange-100 text-orange-800')))}">${m.storageBackend==='mega'?'🟣 MEGA':(m.storageBackend==='oci'?'🔴 Oracle':(m.storageBackend==='gdrive'?'🟢 Google Drive':(m.storageBackend==='r2'?'☁️ R2':'💾 本機')))}</span>` : ''}
                            ${!m.isBuiltin && !m.active ? '<span class="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">已停用</span>' : ''}${!m.isBuiltin&&m.materialType==='atlas'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-teal-50 text-teal-700">🔬 Atlas</span>':''}${!m.isBuiltin&&m.materialType==='infographic'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">📊 資訊圖表</span>':m.materialType==='sop'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-700">📑 SOP</span>':m.materialType==='troubleshooting'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">🧰 Troubleshooting</span>':m.materialType==='case'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-700">🩸 案例分析</span>':''}
                        </div>
                        <div class="text-xs text-slate-500 mt-1">${escapeHtml(m.categoryLabel || '未分類')} · ${m.pageCount || 0} 頁 · ${escapeHtml(m.dateAdded || '')}</div>
                        ${!m.isBuiltin && m.storageMeta ? `<div class="text-[11px] text-slate-400 mt-1">☁ ${m.storageMeta.previewMode==='single_pdf'?'單一預覽檔':'閱讀版'} ${escapeHtml((m.slideFormat||m.storageMeta.slideFormat||'png').toUpperCase())}${m.storageMeta.slideBytes?` · ${formatFileBytes(m.storageMeta.slideBytes)}`:''}${m.storageMeta.sourceBytes?` ｜ 原始檔 ${formatFileBytes(m.storageMeta.sourceBytes)}`:''}${m.storageMeta.cloudObjectCount?` ｜ 雲端檔案 ${m.storageMeta.cloudObjectCount} 個`:''}</div>` : ''}
                    </div>
                    ${m.isBuiltin ? '<span class="text-xs text-slate-400">內建教材不可修改</span>' : `
                        <div class="flex flex-wrap gap-2 shrink-0">
                            <button onclick="editAdminMaterial('${m.id}')" class="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg">✏️ 編輯</button>
                            <button onclick="toggleAdminMaterial('${m.id}', ${m.active ? 'false' : 'true'})" class="text-xs bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded-lg">${m.active ? '⏸️ 停用' : '▶️ 啟用'}</button>
                            <details class="relative"><summary class="list-none cursor-pointer text-[11px] bg-white border border-slate-200 text-slate-500 px-2.5 py-1.5 rounded-lg">更多</summary><div class="absolute right-0 z-20 mt-1 w-40 rounded-xl border border-rose-200 bg-white shadow-lg p-2"><button onclick="deleteAdminMaterial('${m.id}')" class="w-full text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-1.5 rounded-lg">🗑️ 永久刪除</button></div></details>
                        </div>`}
                </div>
            </div>`).join('') || '<p class="text-xs text-slate-400">目前沒有教材。</p>';
    } catch (err) { box.innerHTML = `<p class="text-xs text-rose-500">❌ ${escapeHtml(err.message)}</p>`; }
}

function formatFileBytes(value){const n=Number(value||0);if(!Number.isFinite(n)||n<=0)return '0 B';if(n<1024)return `${Math.round(n)} B`;if(n<1024*1024)return `${(n/1024).toFixed(1)} KB`;if(n<1024*1024*1024)return `${(n/1024/1024).toFixed(1)} MB`;return `${(n/1024/1024/1024).toFixed(2)} GB`;}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

// ==================================================================
// 管理者後台：組別選單、教材分類選單、考題頁籤與題庫管理
// ==================================================================
function groupOptionsForArea(area){return Object.entries(GROUPS).filter(([k,g])=>area==='pgy'||!g.pgyOnly).map(([k,g])=>`<option value="${k}">${escapeHtml(g.label)}</option>`).join('');}
function populateAdminGroupSelects() {
    const opts = groupOptionsForArea(currentTrainingArea);
    const matSel = document.getElementById('admin-material-group');
    const quizSel = document.getElementById('admin-quiz-group');
    const wizardSel = document.getElementById('wizard-group');
    if (matSel) matSel.innerHTML = opts;
    const matArea=document.getElementById('admin-material-area'); const quizArea=document.getElementById('admin-quiz-area');
    if(matArea){matArea.value=currentTrainingArea; matArea.onchange=()=>{if(matSel)matSel.innerHTML=groupOptionsForArea(matArea.value);onAdminMaterialGroupChange();};}
    if(quizArea){quizArea.value=currentTrainingArea; quizArea.onchange=()=>{if(quizSel)quizSel.innerHTML=groupOptionsForArea(quizArea.value);renderAdminQuizCategories();};}
    if (quizSel) quizSel.innerHTML = opts;
    if (wizardSel) {wizardSel.innerHTML = groupOptionsForArea(document.getElementById('wizard-area')?.value || currentTrainingArea); wizardSel.onchange=()=>{renderAdminCourses(true);renderAdminCourseMaterialHub(true);};}
    const wizardArea=document.getElementById('wizard-area');if(wizardArea){wizardArea.onchange=()=>{if(wizardSel){wizardSel.innerHTML=groupOptionsForArea(wizardArea.value);wizardSel.value=wizardSel.options[0]?.value||'';}renderAdminCourses(true);renderAdminCourseMaterialHub(true);};}
}

function onAdminMaterialGroupChange() {
    refreshAdminMaterialCategoryOptions(); refreshAdminMaterialCourses();
}

async function refreshAdminMaterialCategoryOptions() {
    const group = document.getElementById('admin-material-group').value;
    const sel = document.getElementById('admin-material-category');
    if (!sel) return;
    sel.innerHTML = `<option value="">未分類 / 一般補充教材</option>`;
    try {
        const res = await fetch(`/api/quiz-categories?group=${group}&area=${document.getElementById('admin-material-area')?.value || currentTrainingArea}`);
        const cats = await res.json();
        sel.innerHTML += cats.map(c => `<option value="${c.id}">${escapeHtml(c.title)}</option>`).join('');
    } catch (err) { /* 靜默失敗，保留「未分類」選項即可 */ }
}

function onAdminQuizGroupChange() { renderAdminQuizCategories(false); }

function paintAdminQuizCategories(cats){
    const box=document.getElementById('admin-quiz-categories-list'); if(!box)return;
    if(!cats.length){box.innerHTML='<p class="text-xs text-slate-500 py-2">本組別尚未建立任何考題頁籤，請於上方輸入頁籤名稱後點擊「➕ 新增」。</p>';return;}
    box.innerHTML=cats.map(quizCategoryCardHTML).join('');
    updateQuizWorkspacePresentation();
}
function optimisticInsertQuizCategory(cat, area, group){
    const k=adminScopeKey(area,group), cached=adminQuizCategoriesCache.get(k)?.data||[];
    const next=[{...cat,questionCount:Number(cat.questionCount||0)},...cached.filter(c=>c.id!==cat.id)];
    adminQuizCategoriesCache.set(k,{data:next,at:Date.now()});
    const curArea=document.getElementById('admin-quiz-area')?.value||currentTrainingArea, curGroup=document.getElementById('admin-quiz-group')?.value||currentGroupKey;
    if(curArea===area&&curGroup===group){ paintAdminQuizCategories(next); setAdminQuizSyncStatus('剛建立・背景同步中','indigo'); }
}
function patchVisibleQuizCounts(cats){
    for(const c of cats||[]){ const el=document.getElementById(`qcount-${c.id}`); if(el)el.textContent=Number(c.questionCount||0); }
}
async function renderAdminQuizCategories(force=false) {
    const box=document.getElementById('admin-quiz-categories-list');
    const group=document.getElementById('admin-quiz-group')?.value;
    const area=document.getElementById('admin-quiz-area')?.value||currentTrainingArea;
    if(!box||!group)return;
    const k=adminScopeKey(area,group), cached=adminQuizCategoriesCache.get(k), now=Date.now();
    if(cached?.data) paintAdminQuizCategories(cached.data);
    if(!force && cached?.data && (now-cached.at)<ADMIN_QUIZ_CACHE_MS){ setAdminQuizSyncStatus('已快取・可立即操作','emerald'); return; }
    const key=await getAdminKey(); if(!key)return;
    const hasVisibleData=!!cached?.data?.length || !!box.querySelector('article');
    if(!hasVisibleData) box.innerHTML='<div class="space-y-3"><div class="h-20 rounded-2xl bg-slate-100 animate-pulse"></div><div class="h-20 rounded-2xl bg-slate-100 animate-pulse"></div></div>';
    else box.classList.add('opacity-75');
    setAdminQuizSyncStatus('背景同步中…','indigo');
    try{
        const res=await fetch(`/api/quiz-categories/admin?group=${group}&area=${area}`,{headers:{'X-Admin-Key':key}});
        const cats=await res.json().catch(()=>[]); if(!res.ok)throw new Error((cats&&cats.error)||'讀取失敗');
        const list=Array.isArray(cats)?cats:[]; adminQuizCategoriesCache.set(k,{data:list,at:Date.now()});
        // 若使用者正在展開編輯題目，不摧毀現有 DOM；只同步題數與快取。
        if(adminHasExpandedQuestionEditor(box)){ patchVisibleQuizCounts(list); setAdminQuizSyncStatus('已同步・保留目前編輯','emerald'); }
        else { paintAdminQuizCategories(list); setAdminQuizSyncStatus('剛剛同步完成','emerald'); }
    }catch(err){ setAdminQuizSyncStatus('同步失敗','rose'); if(!hasVisibleData)box.innerHTML=`<p class="text-xs text-rose-500">❌ ${escapeHtml(err.message)}</p>`; }
    finally{box.classList.remove('opacity-75');}
}


function quizCategoryCardHTML(c) {
    return `
        <article class="border border-slate-200 rounded-2xl bg-white shadow-sm overflow-hidden">
            <div class="p-4 flex items-start justify-between gap-3 flex-wrap bg-gradient-to-r from-white to-slate-50">
                <div class="min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="font-black text-base text-slate-900 break-all">${escapeHtml(c.title)}</span>
                        <span class="text-[11px] px-2 py-0.5 rounded-full ${c.active?'bg-emerald-50 text-emerald-700':(c.reviewStatus==='approved'?'bg-sky-50 text-sky-700':'bg-amber-100 text-amber-800')} font-bold">${c.active?'已發布':(c.reviewStatus==='approved'?'已審核・待發布':'草稿・待審核')}</span>${c.blindMode?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-slate-900 text-white font-bold">導師設定：盲測</span>':''}
                    </div>
                    <div class="text-xs text-slate-500 mt-1">${escapeHtml(c.desc || '尚未填寫考卷說明')}</div>
                    <div class="flex flex-wrap gap-1.5 mt-2"><span class="text-[10px] px-2 py-1 rounded-full bg-slate-100 text-slate-700">👤 ${escapeHtml(examAudienceLabel(c))}</span><span class="text-[10px] px-2 py-1 rounded-full bg-slate-100 text-slate-700">🧠 題庫 ${Number(c.questionCount||0)} 題</span><span class="text-[10px] px-2 py-1 rounded-full bg-teal-50 text-teal-700">📋 ${escapeHtml(examDrawLabel(c))}</span><span class="text-[10px] px-2 py-1 rounded-full bg-emerald-50 text-emerald-700">🎯 及格 ${Number(c.passingScore||80)} 分</span>${c.publicationHash?`<span class="text-[10px] px-2 py-1 rounded-full bg-violet-50 text-violet-700" title="發布快照 SHA-256：${escapeHtml(c.publicationHash)}">🔒 快照 ${escapeHtml(c.publicationHash.slice(0,10))}</span>`:''}</div>
                </div>
                <div class="flex gap-2 shrink-0 flex-wrap">
                    <button data-admin-role="questions-action" onclick="toggleQuizQuestionsPanel('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-2 rounded-lg font-bold">🧠 題庫／AI（<span id="qcount-${c.id}">${Number.isFinite(Number(c.questionCount)) ? Number(c.questionCount) : 0}</span>）</button>
                    <button data-admin-role="exam-action" onclick="adminEditQuizCategory('${c.id}')" class="text-xs bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">✏️ 考卷設定</button>
                    <button id="blind-toggle-${c.id}" onclick="adminToggleBlindMode('${c.id}',${c.blindMode?'false':'true'})" class="text-xs ${c.blindMode?'bg-slate-900 text-white border-slate-900':'bg-white text-slate-700 border-slate-300'} border hover:bg-slate-100 px-3 py-2 rounded-lg font-bold">🕶️ 盲測：${c.blindMode?'開啟':'關閉'}</button>
                    <button onclick="openQuizMaterialLinker('${c.id}')" class="text-xs bg-white border border-cyan-200 hover:bg-cyan-50 text-cyan-700 px-3 py-2 rounded-lg font-bold">🔗 關聯教材</button>
                    <details class="relative"><summary class="list-none cursor-pointer text-xs bg-white border border-slate-200 text-slate-500 px-3 py-2 rounded-lg">更多</summary><div class="absolute right-0 mt-1 z-30 w-40 bg-white border border-slate-200 shadow-xl rounded-xl p-2"><button onclick="adminDeleteQuizCategory('${c.id}')" class="w-full text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg">🗑️ 刪除考卷</button></div></details>
                </div>
            </div>
            <div id="qpanel-${c.id}" class="hidden border-t border-slate-200 p-4 space-y-4 bg-slate-50/60">
                <section id="qmaterial-link-${c.id}" class="hidden bg-cyan-50/60 rounded-xl border border-cyan-200 p-3 space-y-3">
                    <div class="flex items-start justify-between gap-3 flex-wrap"><div><p class="text-sm font-black text-cyan-950">🔗 重新關聯教材</p><p class="text-[11px] text-cyan-700 mt-1">勾選要綁定此考卷的教材。若教材原本綁定其他考卷，儲存後會改綁到目前考卷。</p></div><button onclick="closeQuizMaterialLinker('${c.id}')" class="text-[11px] text-slate-500 hover:text-slate-800">收合</button></div>
                    <div class="flex gap-2"><input id="qmaterial-search-${c.id}" oninput="filterQuizMaterialLinker('${c.id}')" placeholder="搜尋教材名稱…" class="flex-1 px-3 py-2 border border-cyan-200 rounded-xl text-xs bg-white"><button onclick="saveQuizMaterialLinks('${c.id}')" class="bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-bold px-4 py-2 rounded-xl">💾 儲存關聯</button></div>
                    <div id="qmaterial-list-${c.id}" class="max-h-72 overflow-auto space-y-1.5"><p class="text-xs text-slate-400">讀取教材中…</p></div><div id="qmaterial-status-${c.id}" class="text-[11px] text-cyan-700"></div>
                </section>
                <section class="bg-white rounded-xl border border-slate-200 p-3">
                    <div class="flex items-start justify-between gap-3 mb-3 flex-wrap"><div><p class="text-sm font-black text-slate-900">目前正式題庫</p><p class="text-[11px] text-slate-500">可單題快速編輯，也可全選後一次展開、批次套用分類或啟用狀態。</p></div><span id="qselected-${c.id}" class="text-[11px] px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-bold">已選 0 題</span></div>
                    <div class="mb-3 rounded-xl border border-indigo-100 bg-indigo-50/40 p-2.5 grid sm:grid-cols-[1fr_auto_auto_auto] gap-2"><input id="qfilter-text-${c.id}" oninput="renderFilteredQuestionList('${c.id}')" placeholder="🔎 搜尋題目 / 分類 / 解析" class="px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white"><select id="qfilter-type-${c.id}" onchange="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部題型</option><option value="choice">單選</option><option value="multi">複選</option><option value="true_false">是非</option><option value="fill">填空</option><option value="essay">問答</option><option value="image">圖片</option><option value="video">影片</option></select><select id="qfilter-difficulty-${c.id}" onchange="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部難度</option><option value="basic">基礎</option><option value="standard">一般</option><option value="advanced">進階</option></select><select id="qfilter-active-${c.id}" onchange="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部狀態</option><option value="active">啟用</option><option value="inactive">停用</option></select></div>
                    <div id="qtoolbar-${c.id}" class="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5 flex items-center gap-2 flex-wrap">
                        <label class="text-xs font-bold text-slate-700 inline-flex items-center gap-1.5"><input id="qselect-all-${c.id}" type="checkbox" onchange="adminSelectAllQuestions('${c.id}',this.checked)" class="rounded"> 全選</label>
                        <button onclick="adminEditSelectedQuestions('${c.id}',false)" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold">✏️ 編輯已選</button>
                        <button onclick="adminEditSelectedQuestions('${c.id}',true)" class="text-[11px] bg-violet-700 hover:bg-violet-600 text-white px-3 py-1.5 rounded-lg font-bold">📝 全選編輯</button>
                        <button onclick="adminSaveExpandedQuestionEdits('${c.id}')" class="text-[11px] bg-teal-700 hover:bg-teal-600 text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存展開編輯</button>
                        <span class="h-5 w-px bg-slate-300 hidden sm:block"></span>
                        <button onclick="adminBulkSetQuestionTag('${c.id}')" class="text-[11px] bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg">🏷️ 批次分類</button>
                        <button onclick="adminBulkSetQuestionActive('${c.id}',true)" class="text-[11px] bg-white border border-emerald-200 hover:bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg">▶ 批次啟用</button>
                        <button onclick="adminBulkSetQuestionActive('${c.id}',false)" class="text-[11px] bg-white border border-amber-200 hover:bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg">⏸ 批次停用</button>
                        <button onclick="adminBulkDeleteQuestions('${c.id}')" class="text-[11px] bg-white border border-slate-200 hover:bg-rose-50 text-slate-500 hover:text-rose-700 px-3 py-1.5 rounded-lg">更多：批次刪除</button>
                        <span id="qbulk-progress-${c.id}" class="text-[11px] text-slate-500"></span>
                    </div>
                    <div id="qlist-${c.id}" class="space-y-2"></div><div id="qsticky-save-${c.id}" class="sticky bottom-2 z-20 mt-3 rounded-xl border border-teal-200 bg-white/95 backdrop-blur shadow-lg p-2.5 flex items-center justify-between gap-3"><span class="text-[11px] text-slate-500">批次編輯後可直接在此儲存，不必回頁首。</span><button onclick="adminSaveExpandedQuestionEdits('${c.id}')" class="text-xs bg-teal-700 hover:bg-teal-600 text-white px-4 py-2 rounded-lg font-bold">💾 儲存全部修改</button></div>
                </section>

                <section class="rounded-2xl border border-violet-200 bg-white overflow-hidden">
                    <div class="bg-gradient-to-r from-violet-800 to-indigo-800 text-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
                        <div><p class="font-black">✨ AI 教材出題工作室</p><p class="text-[11px] text-violet-100 mt-0.5">選教材 → 設定題型與難度 → 產生候選題 → 人工審核 → 匯入正式題庫</p></div>
                        <span id="ai-status-${c.id}" class="text-[11px] px-2.5 py-1 rounded-full bg-white/10 ring-1 ring-white/20">檢查 AI 設定中…</span>
                    </div>
                    <div class="p-4 space-y-4">
                        <div class="grid lg:grid-cols-3 gap-3">
                            <div class="lg:col-span-3">
                                <div class="flex items-center justify-between gap-3 mb-2"><label class="block text-xs font-black text-violet-900">① 選擇 AI 要閱讀的教材（可複選）</label><span class="text-[11px] text-slate-500">最多 4 份；影片一次最多 1 支</span></div>
                                <div class="rounded-xl border border-violet-100 bg-violet-50/40 p-3 space-y-2.5">
                                    <div class="flex flex-col lg:flex-row gap-2 lg:items-center">
                                        <div class="relative flex-1"><span class="absolute left-3 top-2.5 text-slate-400 text-xs">🔎</span><input id="ai-material-search-${c.id}" oninput="filterAiMaterials('${c.id}')" placeholder="搜尋教材名稱、檔名…" class="w-full pl-8 pr-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"></div>
                                        <select id="ai-material-scope-${c.id}" onchange="filterAiMaterials('${c.id}',true)" class="px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"><option value="linked">優先：本考卷教材</option><option value="all">查看本組全部教材</option></select>
                                        <select id="ai-material-kind-${c.id}" onchange="filterAiMaterials('${c.id}',true)" class="px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"><option value="all">全部類型</option><option value="text">📄 文件</option><option value="image">🖼️ 圖片 / Atlas</option><option value="video">🎬 影片</option><option value="audio">🎧 音訊</option><option value="subtitle">💬 字幕</option></select>
                                        <button type="button" onclick="recommendAiMaterials('${c.id}')" class="px-3 py-2 rounded-xl bg-white border border-violet-200 text-violet-700 text-xs font-bold hover:bg-violet-50">✨ 建議教材</button>
                                    </div>
                                    <div id="ai-selected-${c.id}" class="min-h-[34px] rounded-lg bg-white border border-violet-100 px-2.5 py-2 text-[11px] text-slate-500">尚未選擇教材</div>
                                    <div id="ai-materials-${c.id}" data-group="${c.group}" data-area="${c.area}" class="space-y-1.5"><div class="text-xs text-slate-400">讀取本組教材中…</div></div>
                                    <div class="flex items-center justify-between gap-2"><span id="ai-material-count-${c.id}" class="text-[11px] text-slate-400"></span><button id="ai-material-more-${c.id}" type="button" onclick="loadMoreAiMaterials('${c.id}')" class="hidden text-[11px] text-violet-700 font-bold hover:underline">顯示更多教材</button></div>
                                </div>
                                <div class="mt-2 text-[11px] text-slate-500">💡 圖片 / Atlas 會直接做視覺分析；影片會擷取代表畫面並結合語音逐字稿。也可把「影片＋字幕＋SOP/PDF」一起選做交叉出題。</div>
                            </div>
                            <div><label class="block text-xs font-bold text-slate-600 mb-1">② 題型</label><select id="ai-type-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="mixed_all">單選＋多選＋填空＋問答</option><option value="mixed_choice_multi">單選＋多選</option><option value="choice">只出單選題</option><option value="multi">只出多選題</option><option value="fill">只出填空題</option><option value="essay">只出問答題</option><option value="mixed">單選＋問答混合</option><option value="video_choice">🎬 影片即時單選題</option><option value="video_multi">🎬 影片即時多選題</option><option value="video_fill">🎬 影片即時填空題</option><option value="video_essay">🎬 影片即時問答題</option><option value="video_mixed">🎬 影片混合互動題</option></select></div>
                            <div><label class="block text-xs font-bold text-slate-600 mb-1">③ 難度</label><select id="ai-difficulty-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="basic">基礎</option><option value="standard" selected>標準</option><option value="advanced">進階</option></select></div>
                            <div><label class="block text-xs font-bold text-slate-600 mb-1">④ 題數</label><select id="ai-count-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="3">3 題</option><option value="5" selected>5 題</option><option value="10">10 題</option><option value="15">15 題</option></select></div>
                            <div><label class="block text-xs font-bold text-slate-600 mb-1">⑤ 出題策略</label><select id="ai-strategy-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="auto" selected>✨ 自動依教材判斷</option><option value="balanced">均衡涵蓋</option><option value="workflow">操作流程</option><option value="scenario">情境／故障排除</option><option value="safety">安全／品質／通報</option><option value="recognition">辨識／圖像判讀</option><option value="regulation">法規／SOP</option></select></div>
                            <div class="lg:col-span-2"><label class="block text-xs font-bold text-slate-600 mb-1">⑥ 特別希望考哪些重點？（選填）</label><input id="ai-focus-${c.id}" type="text" maxlength="500" placeholder="例如：故障排除、QC 設定、法定傳染病通報；留白則由 AI 自動抓重點" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"></div>
                        </div>
                        <div class="flex items-center gap-3 flex-wrap"><button id="ai-generate-${c.id}" onclick="adminGenerateAiQuestions('${c.id}')" class="bg-violet-700 hover:bg-violet-600 text-white px-4 py-2.5 rounded-xl text-sm font-black">✨ 產生候選題</button><span id="ai-progress-${c.id}" class="text-xs text-violet-700"></span></div>
                        <div id="ai-progress-wrap-${c.id}" class="hidden rounded-xl border border-violet-100 bg-violet-50/70 p-3">
                            <div class="flex items-center justify-between gap-3 text-[11px]"><span id="ai-progress-label-${c.id}" class="font-bold text-violet-800">準備 AI 出題…</span><span id="ai-progress-percent-${c.id}" class="font-black text-violet-700">0%</span></div>
                            <div class="mt-2 h-2.5 rounded-full bg-violet-100 overflow-hidden"><div id="ai-progress-bar-${c.id}" class="h-full w-0 rounded-full bg-gradient-to-r from-violet-600 via-fuchsia-500 to-indigo-500 transition-[width] duration-500"></div></div>
                            <div id="ai-progress-detail-${c.id}" class="mt-2 text-[11px] text-violet-600">正在準備教材來源。</div>
                        </div>
                        <div id="ai-candidates-${c.id}" class="space-y-3"></div>
                    </div>
                </section>

                <details class="bg-white rounded-xl border border-slate-200 p-3">
                    <summary class="cursor-pointer text-sm font-black text-slate-800">➕ 其他建題方式：手動新增 / 公開連結批次匯入</summary>
                    <div class="mt-3 grid lg:grid-cols-2 gap-4">
                        <div class="rounded-xl bg-slate-50 p-3 space-y-2">
                            <p class="text-xs font-black text-slate-700">手動新增單題</p>
                            <input id="qform-${c.id}-question" type="text" placeholder="題目內容" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs">
                            <div class="flex gap-2 flex-wrap"><select id="qform-${c.id}-type" onchange="updateManualQuestionType('${c.id}')" class="px-2 py-2 border rounded-lg text-xs"><option value="choice">單選題</option><option value="multi">複選題</option><option value="true_false">是非題</option><option value="fill">填空題</option><option value="essay">問答題</option><option value="image">圖片判讀題</option><option value="video_choice">🎬 影片單選題</option><option value="video_multi">🎬 影片多選題</option><option value="video_fill">🎬 影片填空題</option><option value="video_essay">🎬 影片問答題</option></select><select id="qform-${c.id}-difficulty" class="px-2 py-2 border rounded-lg text-xs"><option value="basic">基礎</option><option value="standard" selected>一般</option><option value="advanced">進階</option></select><input id="qform-${c.id}-image" type="file" accept="image/*" class="text-xs max-w-[220px]"></div>
                            <div id="qform-${c.id}-choice-options" class="grid grid-cols-1 sm:grid-cols-2 gap-2"><input id="qform-${c.id}-opt0" type="text" placeholder="選項 A" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt1" type="text" placeholder="選項 B" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt2" type="text" placeholder="選項 C" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt3" type="text" placeholder="選項 D" class="px-2.5 py-1.5 border rounded-lg text-xs"></div>
                            <div id="qform-${c.id}-choice-answer" class="flex gap-2 items-center"><label class="text-xs text-slate-500">正解</label><select id="qform-${c.id}-correct" class="px-2 py-1.5 border rounded-lg text-xs"><option value="0">A</option><option value="1">B</option><option value="2">C</option><option value="3">D</option></select><input id="qform-${c.id}-tag" type="text" placeholder="分類標籤" class="flex-1 px-2.5 py-1.5 border rounded-lg text-xs"></div>
                            <div id="qform-${c.id}-advanced-answer" class="hidden rounded-lg border border-slate-200 bg-white p-2 space-y-2"><div id="qform-${c.id}-multi-config" class="hidden text-xs"><label class="font-bold text-slate-600">複選正解（可複選）</label><div class="flex gap-3 mt-1">${[0,1,2,3].map(j=>`<label><input id="qform-${c.id}-multi${j}" type="checkbox" class="mr-1">${String.fromCharCode(65+j)}</label>`).join('')}</div></div><div id="qform-${c.id}-truefalse-config" class="hidden text-xs"><label class="font-bold text-slate-600 mr-2">正確答案</label><select id="qform-${c.id}-truefalse-correct" class="px-2 py-1.5 border rounded-lg text-xs"><option value="0">是</option><option value="1">否</option></select></div><div id="qform-${c.id}-fill-config" class="hidden"><label class="text-xs font-bold text-slate-600">可接受答案</label><input id="qform-${c.id}-fill-answers" class="w-full mt-1 px-2 py-1.5 border rounded text-xs" placeholder="多個答案請用 | 分隔，例如：EDTA|乙二胺四乙酸"></div><div id="qform-${c.id}-video-config" class="hidden grid sm:grid-cols-2 gap-2"><input id="qform-${c.id}-media-url" class="px-2 py-1.5 border rounded text-xs" placeholder="影片網址 / 站內媒體網址"><input id="qform-${c.id}-pause-at" type="number" min="0" step="1" class="px-2 py-1.5 border rounded text-xs" placeholder="提示時間（秒）"></div></div>
                            <textarea id="qform-${c.id}-explain" rows="2" placeholder="詳解 / 問答題評分參考" class="w-full px-2.5 py-1.5 border rounded-lg text-xs"></textarea>
                            <button onclick="adminAddQuizQuestion('${c.id}')" class="text-xs bg-teal-700 hover:bg-teal-600 text-white px-3 py-2 rounded-lg font-bold">＋ 新增此題</button>
                        </div>
                        <div class="rounded-xl bg-indigo-50 p-3 space-y-2 self-start"><p class="text-xs font-black text-indigo-900">由公開 JSON / CSV 連結批次匯入</p><p class="text-[11px] text-indigo-700">適合 Google Sheet 發布 CSV 或既有題庫檔案。匯入後仍可逐題修改與停用。</p><input id="qimport-${c.id}" type="url" placeholder="貼上公開 JSON / CSV 網址" class="w-full px-3 py-2 border border-indigo-200 rounded-lg text-xs bg-white"><button onclick="adminImportQuizUrl('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-2 rounded-lg font-bold">🔗 批次匯入</button></div>
                    </div>
                </details>
            </div>
        </article>`;
}


function updateManualQuestionType(catId) {
    const raw=document.getElementById(`qform-${catId}-type`)?.value||'choice',isVideo=raw.startsWith('video_'),type=isVideo?raw.slice(6):raw,needs=['choice','multi','image'].includes(type);
    document.getElementById(`qform-${catId}-choice-options`)?.classList.toggle('hidden',!needs);document.getElementById(`qform-${catId}-choice-answer`)?.classList.toggle('hidden',!['choice','image'].includes(type));document.getElementById(`qform-${catId}-advanced-answer`)?.classList.toggle('hidden',!['multi','true_false','fill'].includes(type)&&!isVideo);document.getElementById(`qform-${catId}-multi-config`)?.classList.toggle('hidden',type!=='multi');document.getElementById(`qform-${catId}-truefalse-config`)?.classList.toggle('hidden',type!=='true_false');document.getElementById(`qform-${catId}-fill-config`)?.classList.toggle('hidden',type!=='fill');document.getElementById(`qform-${catId}-video-config`)?.classList.toggle('hidden',!isVideo);const exp=document.getElementById(`qform-${catId}-explain`);if(exp)exp.placeholder=type==='essay'?'評分重點／參考答案（選填）':(type==='true_false'?'答案依據／解析（選填）':(type==='fill'?'答案解析（選填）':'詳解（選填，作答後顯示）'));
}

const aiQuestionDrafts = {};

async function refreshAiQuestionStatus(catId) {
    const el = document.getElementById(`ai-status-${catId}`);
    if (!el) return;
    const key = await getAdminKey();
    if (!key) return;
    try {
        const res = await fetch('/api/ai-questions/status', {headers:{'X-Admin-Key':key}});
        const d = await res.json();
        if (!res.ok) throw new Error(d.error || '無法檢查 AI');
        if (d.configured) {
            el.className='text-[11px] px-2 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700';
            el.textContent=`✅ AI 已啟用 · ${d.provider==='groq'?'Groq Free':(d.provider==='gemini'?'Google Gemini':'OpenAI')} · ${d.model}${d.mediaSupported?' · 多媒體／多來源':''}${d.freeOnlyMode?' · 免費模式鎖定':''}`;
        } else {
            el.className='text-[11px] px-2 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700';
            el.textContent='⚠️ 尚未設定免費 AI API Key（V5.3.14 預設使用 GROQ_API_KEY）';
        }
    } catch (e) { el.textContent='⚠️ AI 狀態讀取失敗'; }
}

function aiMaterialKind(m) {
    const name=(m.filename||m.title||'').toLowerCase();
    if(/\.(mp4|webm|mov|m4v)$/.test(name)) return ['video','🎬 影片','bg-rose-50 text-rose-700 border-rose-100'];
    if(/\.(mp3|wav|m4a|ogg)$/.test(name)) return ['audio','🎧 音訊','bg-amber-50 text-amber-700 border-amber-100'];
    if(/\.(png|jpg|jpeg|gif|webp)$/.test(name)) return ['image','🖼️ 圖片','bg-sky-50 text-sky-700 border-sky-100'];
    if(/\.(srt|vtt)$/.test(name)) return ['subtitle','💬 字幕','bg-fuchsia-50 text-fuchsia-700 border-fuchsia-100'];
    return ['text','📄 文件','bg-emerald-50 text-emerald-700 border-emerald-100'];
}

const aiMaterialCatalog = {};
const aiMaterialPickerState = {};

function _aiPickerState(catId){
    if(!aiMaterialPickerState[catId]) aiMaterialPickerState[catId]={selected:new Set(),limit:12};
    return aiMaterialPickerState[catId];
}

function _aiMaterialSearchText(m){
    return `${m.title||''} ${m.filename||''} ${m.materialType||''} ${m.atlasCategory||''} ${m.description||''}`.toLowerCase();
}

function updateAiSelectedSummary(catId){
    const state=_aiPickerState(catId), catalog=aiMaterialCatalog[catId]||[];
    const selected=catalog.filter(m=>state.selected.has(String(m.id)));
    const el=document.getElementById(`ai-selected-${catId}`);
    if(!el)return;
    if(!selected.length){el.innerHTML='<span class="text-slate-400">尚未選擇教材（最多 4 份）</span>';return;}
    el.innerHTML=`<div class="flex items-center gap-1.5 flex-wrap"><span class="font-black text-violet-800 mr-1">已選 ${selected.length} / 4</span>${selected.map(m=>`<button type="button" onclick="toggleAiMaterialSelection('${catId}','${String(m.id).replaceAll("'","\\'")}',false)" class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-violet-100 text-violet-800 font-bold max-w-[260px]" title="移除此教材"><span class="truncate">${escapeHtml(m.title||m.filename)}</span><span>×</span></button>`).join('')}</div>`;
}

function toggleAiMaterialSelection(catId,id,checked){
    const state=_aiPickerState(catId), key=String(id);
    if(checked){
        if(!state.selected.has(key) && state.selected.size>=4){alert('一次最多選 4 份教材');renderAiMaterialPicker(catId);return;}
        const m=(aiMaterialCatalog[catId]||[]).find(x=>String(x.id)===key);
        if(m){const [kind]=aiMaterialKind(m); if(kind==='video' && [...state.selected].some(sid=>{const sm=(aiMaterialCatalog[catId]||[]).find(x=>String(x.id)===sid);return sm&&aiMaterialKind(sm)[0]==='video';})){alert('一次最多選 1 支影片；可再搭配字幕、圖片或文件');renderAiMaterialPicker(catId);return;}}
        state.selected.add(key);
    }else state.selected.delete(key);
    updateAiSelectedSummary(catId); renderAiMaterialPicker(catId,true);
}

function _filteredAiMaterials(catId){
    const catalog=aiMaterialCatalog[catId]||[], state=_aiPickerState(catId);
    const q=(document.getElementById(`ai-material-search-${catId}`)?.value||'').trim().toLowerCase();
    const scope=document.getElementById(`ai-material-scope-${catId}`)?.value||'linked';
    const kindFilter=document.getElementById(`ai-material-kind-${catId}`)?.value||'all';
    let list=catalog.filter(m=>{
        const [kind]=aiMaterialKind(m);
        if(kindFilter!=='all' && kind!==kindFilter)return false;
        if(q && !_aiMaterialSearchText(m).includes(q))return false;
        return true;
    });
    // 「本考卷教材」是優先排序而非完全隱藏，避免找不到跨課程 SOP/影片。
    list.sort((a,b)=>{
        const as=state.selected.has(String(a.id))?0:(a.category===catId?1:2);
        const bs=state.selected.has(String(b.id))?0:(b.category===catId?1:2);
        if(scope==='all') return (state.selected.has(String(a.id))?0:1)-(state.selected.has(String(b.id))?0:1) || String(a.title||a.filename).localeCompare(String(b.title||b.filename),'zh-Hant');
        return as-bs || String(a.title||a.filename).localeCompare(String(b.title||b.filename),'zh-Hant');
    });
    return list;
}

function renderAiMaterialPicker(catId,keepLimit=false){
    const box=document.getElementById(`ai-materials-${catId}`); if(!box)return;
    const state=_aiPickerState(catId); if(!keepLimit)state.limit=12;
    const all=_filteredAiMaterials(catId), selectedIds=state.selected;
    // 已選項目永遠顯示，未選才受分頁限制。
    const selected=all.filter(m=>selectedIds.has(String(m.id)));
    const unselected=all.filter(m=>!selectedIds.has(String(m.id)));
    const visible=[...selected,...unselected.slice(0,Math.max(0,state.limit-selected.length))];
    if(!visible.length){box.innerHTML='<div class="rounded-lg border border-dashed border-slate-300 bg-white p-3 text-xs text-slate-500">沒有符合搜尋/篩選條件的教材。</div>';}
    else box.innerHTML=visible.map(m=>{
        const [kind,label,cls]=aiMaterialKind(m), isSelected=selectedIds.has(String(m.id));
        const linked=m.category===catId;
        return `<label class="flex items-center gap-3 rounded-xl border ${isSelected?'border-violet-300 bg-violet-50':'border-slate-200 bg-white'} px-3 py-2.5 hover:border-violet-300 hover:shadow-sm transition-all cursor-pointer">
            <input type="checkbox" ${isSelected?'checked':''} onchange="toggleAiMaterialSelection('${catId}','${String(m.id).replaceAll("'","\\'")}',this.checked)" class="rounded shrink-0">
            <div class="min-w-0 flex-1"><div class="flex items-center gap-1.5 flex-wrap"><span class="text-[10px] px-2 py-0.5 rounded-full border ${cls} font-bold">${label}</span>${linked?'<span class="text-[10px] px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 font-bold">本考卷</span>':''}</div><p class="mt-1 text-xs font-bold text-slate-800 truncate" title="${escapeHtml(m.title||m.filename)}">${escapeHtml(m.title||m.filename)}</p><p class="text-[10px] text-slate-400 truncate">${escapeHtml(m.filename||'')}</p></div>
        </label>`;
    }).join('');
    const count=document.getElementById(`ai-material-count-${catId}`); if(count)count.textContent=`符合 ${all.length} 份教材 · 已選 ${selectedIds.size} 份`;
    const more=document.getElementById(`ai-material-more-${catId}`); if(more){const remaining=Math.max(0,unselected.length-Math.max(0,state.limit-selected.length));more.classList.toggle('hidden',remaining<=0);more.textContent=remaining>0?`顯示更多教材（尚有 ${remaining} 份）`:'顯示更多教材';}
    updateAiSelectedSummary(catId);
}

function filterAiMaterials(catId,resetLimit=false){if(resetLimit)_aiPickerState(catId).limit=12;renderAiMaterialPicker(catId,true);}
function loadMoreAiMaterials(catId){_aiPickerState(catId).limit+=12;renderAiMaterialPicker(catId,true);}
function recommendAiMaterials(catId){
    const state=_aiPickerState(catId), catalog=aiMaterialCatalog[catId]||[];
    const linked=catalog.filter(m=>m.category===catId);
    const pool=linked.length?linked:catalog;
    state.selected=new Set(pool.slice(0,4).map(m=>String(m.id)));
    // 如果推薦裡有多支影片，只留第一支，補其他非影片教材。
    let videoSeen=false;
    for(const id of [...state.selected]){const m=catalog.find(x=>String(x.id)===id);if(m&&aiMaterialKind(m)[0]==='video'){if(videoSeen)state.selected.delete(id);else videoSeen=true;}}
    for(const m of pool){if(state.selected.size>=4)break;if(!state.selected.has(String(m.id)) && (aiMaterialKind(m)[0]!=='video'||!videoSeen)){state.selected.add(String(m.id));if(aiMaterialKind(m)[0]==='video')videoSeen=true;}}
    renderAiMaterialPicker(catId,true);
}

async function loadAiMaterialOptions(catId) {
    const box=document.getElementById(`ai-materials-${catId}`);
    if(!box) return;
    const group=box.dataset.group || '';
    const area=box.dataset.area || currentTrainingArea;
    box.innerHTML='<div class="text-xs text-slate-400">讀取本組教材中…</div>';
    try {
        const res=await fetch(`/api/slides?area=${encodeURIComponent(area)}`);
        const list=await res.json();
        const mats=(Array.isArray(list)?list:[]).filter(m=>m.group===group && (m.area||'internal')===area && !m.isBuiltin);
        aiMaterialCatalog[catId]=mats;
        const state=_aiPickerState(catId);
        // 首次載入只自動選一份「已對應本考卷」教材，不替使用者亂選其他來源。
        if(!state.selected.size){const linked=mats.find(m=>m.category===catId);if(linked)state.selected.add(String(linked.id));}
        if(!mats.length){box.innerHTML='<div class="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-xs text-slate-500">尚無可供 AI 讀取的教材，請先到「課程與教材」上傳 PPT/PDF/圖片/影音/字幕。</div>';updateAiSelectedSummary(catId);return;}
        renderAiMaterialPicker(catId);
    } catch(e){box.innerHTML='<div class="text-xs text-rose-500">教材清單讀取失敗</div>';}
}

function selectedAiMaterials(catId){
    const state=_aiPickerState(catId), catalog=aiMaterialCatalog[catId]||[];
    return [...state.selected].map(id=>{const m=catalog.find(x=>String(x.id)===String(id));if(!m)return null;return {id:String(m.id),kind:aiMaterialKind(m)[0]};}).filter(Boolean);
}


function renderAiQuestionCandidates(catId, questions, meta={}) {
    aiQuestionDrafts[catId]=questions || [];
    const box=document.getElementById(`ai-candidates-${catId}`);
    if(!box) return;
    if(!questions?.length){box.innerHTML='';return;}
    const cards=questions.map((q,i)=>{
        const t=q.questionType||'choice', opts=(q.options||[]), cfg=q.answerConfig||{};
        let answerHtml='';
        if(['choice','multi'].includes(t)){
            answerHtml=`<div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 mt-2">${[0,1,2,3].map(j=>`<div class="flex items-center gap-1.5"><span class="text-[11px] font-bold text-slate-500 w-4">${String.fromCharCode(65+j)}</span><input id="aid-${catId}-${i}-opt${j}" value="${escapeHtml(opts[j]||'')}" class="flex-1 px-2 py-1.5 border rounded-lg text-xs"></div>`).join('')}</div>`;
            if(t==='multi') answerHtml+=`<div class="mt-2 flex items-center gap-3 flex-wrap text-[11px]"><span class="text-slate-500">正解（複選）</span>${[0,1,2,3].map(j=>`<label><input id="aid-${catId}-${i}-multi${j}" type="checkbox" ${((cfg.correctIndices||[]).map(Number).includes(j))?'checked':''} class="mr-1">${String.fromCharCode(65+j)}</label>`).join('')}</div>`;
            else answerHtml+=`<div class="mt-2 flex items-center gap-2"><label class="text-[11px] text-slate-500">正解</label><select id="aid-${catId}-${i}-correct" class="px-2 py-1 border rounded text-xs">${[0,1,2,3].map(j=>`<option value="${j}" ${Number(q.correct)===j?'selected':''}>${String.fromCharCode(65+j)}</option>`).join('')}</select></div>`;
        } else if(t==='fill') {
            answerHtml=`<div class="mt-2"><label class="text-[11px] text-slate-500">可接受答案（用 | 分隔）</label><input id="aid-${catId}-${i}-accepted" value="${escapeHtml((cfg.acceptedAnswers||[]).join(' | '))}" class="w-full mt-1 px-2 py-1.5 border rounded-lg text-xs"></div>`;
        } else {
            answerHtml='<p class="text-[11px] text-amber-700 mt-2">問答題：正式作答後由考核者人工批改。</p>';
        }
        const videoHtml=cfg.mediaUrl?`<div class="mt-2 rounded-lg bg-rose-50 border border-rose-100 p-2 flex items-center gap-2 flex-wrap"><span class="text-[11px] font-bold text-rose-700">🎬 影片即時題</span><label class="text-[11px] text-slate-500">暫停時間(秒)</label><input id="aid-${catId}-${i}-pause" type="number" min="0" step="1" value="${Number(cfg.pauseAt||0)}" class="w-24 px-2 py-1 border rounded text-xs"></div>`:'';
        const badge=t==='multi'?'多選題':t==='fill'?'填空題':t==='essay'?'問答題':'單選題';
        return `<div class="bg-white border border-violet-100 rounded-xl p-3 shadow-sm"><div class="flex items-start gap-2"><input id="aid-${catId}-${i}-check" type="checkbox" checked class="mt-1"><div class="flex-1 min-w-0"><div class="flex items-center gap-2 flex-wrap"><span class="text-[11px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">${cfg.mediaUrl?'🎬 ':''}${badge}</span><span class="text-[11px] text-slate-400">${escapeHtml(q.sourceHint||'')}</span></div>${q.sourceEvidence?`<div class="mt-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-2 py-1">依據：${escapeHtml(q.sourceEvidence)}</div>`:''}<textarea id="aid-${catId}-${i}-question" rows="2" class="w-full mt-2 px-2.5 py-2 border rounded-lg text-xs">${escapeHtml(q.question||'')}</textarea>${answerHtml}${videoHtml}<div class="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2"><input id="aid-${catId}-${i}-tag" value="${escapeHtml(q.tag||'')}" placeholder="分類標籤" class="px-2 py-1.5 border rounded-lg text-xs"><textarea id="aid-${catId}-${i}-explain" rows="2" placeholder="詳解 / 評分參考" class="px-2 py-1.5 border rounded-lg text-xs">${escapeHtml(q.explanation||'')}</textarea></div></div></div></div>`;
    }).join('');
    box.innerHTML=`<div class="flex items-center justify-between gap-2 flex-wrap pt-1"><p class="text-[11px] text-violet-700">已產生 ${questions.length} 題${meta.sourceCount?`（${meta.sourceCount} 份來源）`:''}</p><button onclick="adminImportAiCandidates('${catId}')" class="text-xs bg-emerald-700 hover:bg-emerald-600 text-white px-3 py-1.5 rounded-lg font-semibold">✅ 將勾選題目加入正式題庫</button></div>${cards}`;
}

function setAiProgressUi(catId,percent,label,detail=''){
    const wrap=document.getElementById(`ai-progress-wrap-${catId}`),bar=document.getElementById(`ai-progress-bar-${catId}`),pct=document.getElementById(`ai-progress-percent-${catId}`),lab=document.getElementById(`ai-progress-label-${catId}`),det=document.getElementById(`ai-progress-detail-${catId}`);
    const v=Math.max(0,Math.min(100,Number(percent)||0)); wrap?.classList.remove('hidden'); if(bar)bar.style.width=`${v}%`; if(pct)pct.textContent=`${Math.round(v)}%`; if(lab&&label)lab.textContent=label; if(det)det.textContent=detail||'';
}
async function pollAiProgress(catId,progressId,key,stop){
    while(!stop.done){
        try{const r=await fetch(`/api/slides/upload-progress/${encodeURIComponent(progressId)}`,{headers:{'X-Admin-Key':key}});const d=await r.json().catch(()=>({}));if(r.ok&&d){setAiProgressUi(catId,d.percent||0,d.stage||'AI 處理中…',d.detail||'');if(Number(d.percent)>=100)break;}}catch(_e){}
        await new Promise(r=>setTimeout(r,650));
    }
}

async function adminGenerateAiQuestions(catId) {
    const key=await getAdminKey(); if(!key)return;
    const selected=selectedAiMaterials(catId);
    if(!selected.length){alert('請至少勾選一份教材');return;}
    if(selected.length>4){alert('一次最多選 4 份教材');return;}
    if(selected.filter(x=>x.kind==='video').length>1){alert('一次最多選 1 支影片；可搭配字幕、圖片或文件');return;}
    const aiType=document.getElementById(`ai-type-${catId}`).value; if(aiType.startsWith('video_')&&!selected.some(x=>x.kind==='video')){alert('影片即時題需要先勾選一支影片教材');return;}
    const btn=document.getElementById(`ai-generate-${catId}`),st=document.getElementById(`ai-progress-${catId}`);
    const progressId=`ai-${Date.now()}-${Math.random().toString(36).slice(2,10)}`, stop={done:false};
    btn.disabled=true;btn.textContent='⏳ AI 出題中…';st.textContent='AI 正在處理教材，進度會顯示於下方。';setAiProgressUi(catId,2,'準備 AI 出題','正在驗證教材、題型與考卷設定');
    const polling=pollAiProgress(catId,progressId,key,stop);
    try{
        const res=await fetch('/api/ai-questions/generate',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({progressId,quizCategoryId:catId,materialIds:selected.map(x=>x.id),count:Number(document.getElementById(`ai-count-${catId}`).value||5),questionType:aiType,difficulty:document.getElementById(`ai-difficulty-${catId}`).value,strategy:document.getElementById(`ai-strategy-${catId}`).value,focus:document.getElementById(`ai-focus-${catId}`).value.trim()})});
        const d=await res.json().catch(()=>({}));if(!res.ok)throw new Error(d.error||'AI 出題失敗');
        setAiProgressUi(catId,100,'AI 候選題完成',`已產生 ${d.questions?.length||0} 題，請人工核對來源與答案。`);
        renderAiQuestionCandidates(catId,d.questions,d);const strategyNames={balanced:'均衡涵蓋',workflow:'操作流程',scenario:'情境／故障排除',safety:'安全／品質／通報',recognition:'辨識／圖像判讀',regulation:'法規／SOP'};const sname=strategyNames[d.strategyApplied]||d.strategyApplied||'';st.textContent=`✅ ${d.model||'AI'} 已分析 ${d.sourceCount||selected.length} 份教材${d.strategyRequested==='auto'&&sname?`（自動策略：${sname}）`:''}；候選題已在下方。`;
        document.getElementById(`ai-candidates-${catId}`)?.scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){setAiProgressUi(catId,0,'AI 出題未完成',e.message);st.textContent=`❌ ${e.message}`;alert(e.message);}
    finally{stop.done=true;await Promise.race([polling,new Promise(r=>setTimeout(r,800))]);btn.disabled=false;btn.textContent='✨ 智慧分析並產生候選題';}
}


function collectAiCandidate(catId, i, original) {
    const question=document.getElementById(`aid-${catId}-${i}-question`)?.value.trim()||'', tag=document.getElementById(`aid-${catId}-${i}-tag`)?.value.trim()||'', explanation=document.getElementById(`aid-${catId}-${i}-explain`)?.value.trim()||'';
    const t=original.questionType||'choice', cfg={...(original.answerConfig||{})};
    if(cfg.mediaUrl) cfg.pauseAt=Number(document.getElementById(`aid-${catId}-${i}-pause`)?.value||0);
    if(t==='essay') return {questionType:'essay',question,options:[],correct:0,answerConfig:cfg,tag,explanation};
    if(t==='fill') { cfg.acceptedAnswers=(document.getElementById(`aid-${catId}-${i}-accepted`)?.value||'').split('|').map(x=>x.trim()).filter(Boolean); cfg.caseSensitive=false; return {questionType:'fill',question,options:[],correct:0,answerConfig:cfg,tag,explanation}; }
    const options=[0,1,2,3].map(j=>document.getElementById(`aid-${catId}-${i}-opt${j}`)?.value.trim()||'');
    if(t==='multi') { cfg.correctIndices=[0,1,2,3].filter(j=>document.getElementById(`aid-${catId}-${i}-multi${j}`)?.checked); return {questionType:'multi',question,options,correct:cfg.correctIndices[0]||0,answerConfig:cfg,tag,explanation}; }
    const correct=Number(document.getElementById(`aid-${catId}-${i}-correct`)?.value||0);
    return {questionType:'choice',question,options,correct,answerConfig:cfg,tag,explanation};
}

async function adminImportAiCandidates(catId) {
    const drafts=aiQuestionDrafts[catId]||[], selected=[];
    drafts.forEach((q,i)=>{if(document.getElementById(`aid-${catId}-${i}-check`)?.checked)selected.push(collectAiCandidate(catId,i,q));});
    const selectedDifficulty=document.getElementById(`ai-difficulty-${catId}`)?.value||'standard';selected.forEach(q=>q.difficulty=selectedDifficulty);
    if(!selected.length){alert('請至少勾選一題');return;}
    for(const q of selected){if(!q.question){alert('有勾選題目的題幹是空白');return;}if(['choice','multi'].includes(q.questionType)&&q.options.some(x=>!x)){alert('單選／多選題 A～D 四個選項都必須填寫');return;}if(q.questionType==='multi'&&!q.answerConfig?.correctIndices?.length){alert('多選題至少要勾選一個正確答案');return;}if(q.questionType==='fill'&&!q.answerConfig?.acceptedAnswers?.length){alert('填空題至少要設定一個可接受答案');return;}}
    if(!confirm(`確定將 ${selected.length} 題加入正式題庫？加入後仍可逐題編輯或刪除。`))return;
    const key=await getAdminKey();if(!key)return;
    const status=document.getElementById(`ai-progress-${catId}`);if(status)status.textContent=`⏳ 正在批次寫入 ${selected.length} 題…`;
    const res=await fetch('/api/ai-questions/import',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({quizCategoryId:catId,questions:selected})});
    const d=await res.json().catch(()=>({}));if(!res.ok){if(status)status.textContent=`❌ ${d.error||'匯入失敗'}`;alert(d.error||'匯入失敗');return;}
    const inserted=Array.isArray(d.questions)?d.questions:[];const listBox=document.getElementById(`qlist-${catId}`);let cache=adminQuizQuestionCache[catId]||[];
    if(inserted.length){cache=[...cache,...inserted];adminQuizQuestionCache[catId]=cache;if(listBox)renderFilteredQuestionList(catId);const countEl=document.getElementById(`qcount-${catId}`);if(countEl)countEl.textContent=cache.filter(q=>q.active!==false).length;adminUpdateQuestionSelection(catId);}
    aiQuestionDrafts[catId]=[];const box=document.getElementById(`ai-candidates-${catId}`);if(box)box.innerHTML='';delete allQuizData[catId];
    if(status)status.textContent=`✅ 已立即加入 ${d.imported||inserted.length||0} 題，背景同步完成。`;
    // 不整份重載題庫；只在背景確認題數，避免畫面卡住/閃白。
    loadQuizQuestionCountOnly(catId);
}

async function loadQuizQuestionCountOnly(catId) {
    try {
        const res = await fetch(`/api/quiz-questions?category=${catId}`);
        const qs = await res.json();
        const el = document.getElementById(`qcount-${catId}`);
        if (el) el.textContent = qs.length;
    } catch (err) { /* 忽略 */ }
}

async function toggleQuizQuestionsPanel(catId) {
    const panel = document.getElementById(`qpanel-${catId}`);
    if (!panel) return;
    const wasHidden = panel.classList.contains('hidden');
    panel.classList.toggle('hidden');
    if (wasHidden) {
        await loadQuizQuestionsIntoPanel(catId);
        await loadAiMaterialOptions(catId);
        await refreshAiQuestionStatus(catId);
    }
}

const adminQuizQuestionCache = {};

function adminAnswerSummary(q) {
    const type=q.questionType||'choice';
    if(type==='essay') return `人工批改 · 評分參考：${escapeHtml(q.explanation||'未設定')}`;
    if(type==='fill') return `可接受答案：${escapeHtml((q.answerConfig?.acceptedAnswers||[]).join(' / ')||'未設定')}`;
    if(type==='multi') {
        const letters=(q.answerConfig?.correctIndices||[]).map(i=>String.fromCharCode(65+Number(i))).join('、');
        return `正解：${escapeHtml(letters||'未設定')}`;
    }
    return `正解：${escapeHtml((q.options||[])[q.correct] ?? '未設定')}`;
}

function adminQuestionEditFormHTML(q,catId){
    const type=q.questionType||'choice',opts=[...(q.options||[])];while(opts.length<6)opts.push('');const cfg=q.answerConfig||{},set=new Set((cfg.correctIndices||[]).map(Number)),hasMedia=!!cfg.mediaUrl,typeOptions=[['choice','單選題'],['multi','複選題'],['true_false','是非題'],['essay','問答題'],['fill','填空題'],['image','圖片判讀題'],['video','影片題']],optionType=['choice','multi','image','video'].includes(type);
    return `<div id="qedit-${q.id}" data-qid="${q.id}" data-has-media="${hasMedia?'1':'0'}" class="hidden mt-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3 space-y-2.5"><div class="flex items-center justify-between gap-2"><span class="text-xs font-black text-indigo-900">快速編輯題目</span><button onclick="adminToggleInlineQuestionEditor('${q.id}','${catId}',false)" class="text-[11px] text-slate-500 hover:text-slate-800">收合</button></div><textarea data-field="question" rows="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white" placeholder="題目內容">${escapeHtml(q.question||'')}</textarea><div class="grid sm:grid-cols-3 gap-2"><label><span class="text-[11px] font-bold text-slate-600">題目類型</span><select data-field="questionType" onchange="adminInlineQuestionTypeChanged('${q.id}')" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white">${typeOptions.map(([v,t])=>`<option value="${v}" ${type===v?'selected':''}>${t}</option>`).join('')}</select></label><label><span class="text-[11px] font-bold text-slate-600">難度</span><select data-field="difficulty" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="basic" ${q.difficulty==='basic'?'selected':''}>基礎</option><option value="standard" ${(q.difficulty||'standard')==='standard'?'selected':''}>一般</option><option value="advanced" ${q.difficulty==='advanced'?'selected':''}>進階</option></select></label><label><span class="text-[11px] font-bold text-slate-600">題目分類</span><input data-field="tag" value="${escapeHtml(q.tag||'')}" placeholder="分類標籤" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"></label></div><div data-role="optionFields" class="${optionType?'':'hidden'} grid sm:grid-cols-2 gap-2">${opts.map((v,i)=>`<input data-field="opt${i}" value="${escapeHtml(v)}" placeholder="選項 ${String.fromCharCode(65+i)}" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white">`).join('')}</div><div data-role="choiceCorrect" class="${['choice','image','video'].includes(type)?'':'hidden'} flex items-center gap-2"><label class="text-[11px] font-bold text-slate-600">正確答案</label><select data-field="correct" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white">${opts.map((_,i)=>`<option value="${i}" ${Number(q.correct||0)===i?'selected':''}>${String.fromCharCode(65+i)}</option>`).join('')}</select></div><div data-role="multiConfig" class="${type==='multi'?'':'hidden'} flex gap-3 flex-wrap text-xs"><span class="font-bold text-slate-600">複選正確答案</span>${opts.map((_,i)=>`<label><input data-field="multi${i}" type="checkbox" ${set.has(i)?'checked':''} class="mr-1">${String.fromCharCode(65+i)}</label>`).join('')}</div><div data-role="trueFalseConfig" class="${type==='true_false'?'':'hidden'}"><label class="text-[11px] font-bold text-slate-600">正確答案</label><select data-field="trueFalseCorrect" class="ml-2 px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="0" ${Number(q.correct||0)===0?'selected':''}>是</option><option value="1" ${Number(q.correct||0)===1?'selected':''}>否</option></select></div><div data-role="fillConfig" class="${type==='fill'?'':'hidden'}"><label class="text-[11px] font-bold text-slate-600">可接受答案（以 | 分隔）</label><input data-field="fillAnswers" value="${escapeHtml((cfg.acceptedAnswers||[]).join(' | '))}" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"></div><div data-role="mediaConfig" class="${(type==='video'||hasMedia)?'':'hidden'} grid sm:grid-cols-2 gap-2"><input data-field="mediaUrl" value="${escapeHtml(cfg.mediaUrl||'')}" placeholder="影片 / 媒體網址" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"><input data-field="pauseAt" type="number" min="0" step="1" value="${Number(cfg.pauseAt||0)}" placeholder="暫停秒數" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"></div><label class="inline-flex items-center gap-2 px-2.5 py-2 border border-slate-300 rounded-lg bg-white text-xs"><input data-field="active" type="checkbox" ${q.active===false?'':'checked'}> 啟用此題</label><textarea data-field="explanation" rows="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white" placeholder="${type==='essay'?'評分重點 / 參考答案':'詳解 / 答案依據'}">${escapeHtml(q.explanation||'')}</textarea><div class="flex gap-2"><button id="qsave-${q.id}" onclick="adminSaveOneInlineQuestion('${q.id}','${catId}')" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 disabled:bg-slate-400 disabled:cursor-wait text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存此題</button></div></div>`;
}
function adminInlineQuestionTypeChanged(qId){const box=document.getElementById(`qedit-${qId}`);if(!box)return;const type=box.querySelector('[data-field="questionType"]')?.value||'choice',toggle=(role,show)=>box.querySelector(`[data-role="${role}"]`)?.classList.toggle('hidden',!show);toggle('optionFields',['choice','multi','image','video'].includes(type));toggle('choiceCorrect',['choice','image','video'].includes(type));toggle('multiConfig',type==='multi');toggle('trueFalseConfig',type==='true_false');toggle('fillConfig',type==='fill');toggle('mediaConfig',type==='video'||box.dataset.hasMedia==='1');const exp=box.querySelector('[data-field="explanation"]');if(exp)exp.placeholder=type==='essay'?'評分重點 / 參考答案':'詳解 / 答案依據';}

function adminQuestionRowHTML(q,i,catId){
    return `<div id="qrow-${q.id}" class="border ${q.active===false?'border-amber-200 bg-amber-50/50':'border-slate-200 bg-white'} rounded-xl p-3">
        <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1 text-xs flex items-start gap-2.5">
                <input type="checkbox" class="qselect-${catId} mt-1 rounded" data-qid="${q.id}" onchange="adminUpdateQuestionSelection('${catId}')">
                <div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="font-bold text-slate-800">${i+1}. ${escapeHtml(q.question)}</span><span class="text-[10px] px-2 py-0.5 rounded-full ${q.active===false?'bg-amber-100 text-amber-800':'bg-emerald-50 text-emerald-700'}">${q.active===false?'停用':'啟用'}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">${questionTypeLabel(q.questionType||'choice')}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">${({basic:'基礎',standard:'一般',advanced:'進階'})[q.difficulty||'standard']||'一般'}</span></div><div class="text-slate-500 mt-1">${adminAnswerSummary(q)}${q.tag?' · 分類：'+escapeHtml(q.tag):''}</div></div>
            </div>
            <div class="flex gap-1.5 shrink-0 flex-wrap justify-end"><button onclick="adminToggleQuizQuestion('${q.id}','${catId}',${q.active===false?'true':'false'})" class="text-[11px] ${q.active===false?'bg-emerald-600 hover:bg-emerald-500':'bg-amber-500 hover:bg-amber-400'} text-white px-2.5 py-1.5 rounded-lg">${q.active===false?'▶ 啟用':'⏸ 停用'}</button><button onclick="adminToggleInlineQuestionEditor('${q.id}','${catId}',true)" class="text-[11px] bg-indigo-600 hover:bg-indigo-500 text-white px-2.5 py-1.5 rounded-lg">✏️ 快速編輯</button><button onclick="adminDeleteQuizQuestion('${q.id}','${catId}')" class="text-[11px] bg-rose-600 hover:bg-rose-500 text-white px-2.5 py-1.5 rounded-lg">🗑️</button></div>
        </div>${adminQuestionEditFormHTML(q,catId)}
    </div>`;
}

function adminSelectedQuestionIds(catId){return [...document.querySelectorAll(`.qselect-${catId}:checked`)].map(x=>x.dataset.qid).filter(Boolean);}
function adminUpdateQuestionSelection(catId){const all=[...document.querySelectorAll(`.qselect-${catId}`)],selected=all.filter(x=>x.checked);const badge=document.getElementById(`qselected-${catId}`);if(badge)badge.textContent=`已選 ${selected.length} 題`;const master=document.getElementById(`qselect-all-${catId}`);if(master){master.checked=all.length>0&&selected.length===all.length;master.indeterminate=selected.length>0&&selected.length<all.length;}}
function adminSelectAllQuestions(catId,checked){document.querySelectorAll(`.qselect-${catId}`).forEach(x=>x.checked=checked);adminUpdateQuestionSelection(catId);}
function adminToggleInlineQuestionEditor(qId,catId,open=true){const el=document.getElementById(`qedit-${qId}`);if(!el)return;el.classList.toggle('hidden',!open);if(open){const cb=document.querySelector(`.qselect-${catId}[data-qid="${qId}"]`);if(cb)cb.checked=true;adminUpdateQuestionSelection(catId);}}
function adminEditSelectedQuestions(catId,selectAll=false){if(selectAll)adminSelectAllQuestions(catId,true);let ids=adminSelectedQuestionIds(catId);if(!ids.length){alert('請先勾選要編輯的題目，或按「全選編輯」。');return;}if(ids.length>80&&!confirm(`即將一次展開 ${ids.length} 題，頁面可能較長，是否繼續？`))return;ids.forEach(id=>adminToggleInlineQuestionEditor(id,catId,true));document.getElementById(`qedit-${ids[0]}`)?.scrollIntoView({behavior:'smooth',block:'center'});}

function adminPayloadFromQuestionEditor(qId,catId){
    const q=(adminQuizQuestionCache[catId]||[]).find(x=>x.id===qId);if(!q)throw new Error('找不到題目資料');const box=document.getElementById(`qedit-${qId}`);if(!box)throw new Error('找不到編輯區');const get=f=>box.querySelector(`[data-field="${f}"]`),type=get('questionType')?.value||q.questionType||'choice',cfg={...(q.answerConfig||{})},payload={question:(get('question')?.value||'').trim(),questionType:type,difficulty:get('difficulty')?.value||q.difficulty||'standard',imageUrl:q.imageUrl||'',tag:(get('tag')?.value||'').trim(),explanation:(get('explanation')?.value||'').trim(),active:!!get('active')?.checked,answerConfig:cfg};if(!payload.question)throw new Error('題目內容不能空白');
    if(['choice','multi','image','video'].includes(type)){const opts=[...box.querySelectorAll('[data-field^="opt"]')].map(x=>x.value.trim()).filter(Boolean);if(opts.length<2)throw new Error('此題型至少需要 2 個選項');payload.options=opts;if(type==='multi'){const indices=opts.map((_,i)=>get(`multi${i}`)?.checked?i:null).filter(i=>i!==null);if(!indices.length)throw new Error('複選題至少需要一個正確答案');payload.correct=indices[0];payload.answerConfig={...cfg,correctIndices:indices};}else payload.correct=Math.max(0,Math.min(opts.length-1,Number(get('correct')?.value||0)));}else if(type==='true_false'){payload.options=['是','否'];payload.correct=Number(get('trueFalseCorrect')?.value||0);payload.answerConfig={};}else{payload.options=[];payload.correct=0;}
    if(type==='fill'){const arr=(get('fillAnswers')?.value||'').split('|').map(x=>x.trim()).filter(Boolean);if(!arr.length)throw new Error('填空題至少要有一個可接受答案');payload.answerConfig={...cfg,acceptedAnswers:arr,caseSensitive:!!cfg.caseSensitive};}const mediaUrl=(get('mediaUrl')?.value||'').trim();if(mediaUrl)payload.answerConfig={...payload.answerConfig,mediaUrl,pauseAt:Math.max(0,Number(get('pauseAt')?.value||0))};else if(type==='video')throw new Error('影片題請填入影片 / 媒體網址');return payload;
}

const questionActionBusy=new Set();
const questionBulkBusy=new Set();
function setQuestionRowBusy(qId,busy,label='處理中…'){
    const row=document.getElementById(`qrow-${qId}`); if(!row)return;
    row.classList.toggle('opacity-60',busy); row.classList.toggle('pointer-events-none',busy);
    row.querySelectorAll('button,input,textarea,select').forEach(el=>{if(busy){el.dataset.prevDisabled=el.disabled?'1':'0';el.disabled=true;}else if(el.dataset.prevDisabled==='0'){el.disabled=false;delete el.dataset.prevDisabled;}});
    let badge=row.querySelector('[data-qbusy]');
    if(busy){if(!badge){badge=document.createElement('div');badge.dataset.qbusy='1';badge.className='mt-2 text-[11px] font-bold text-indigo-700';row.appendChild(badge);}badge.textContent=`⏳ ${label}`;}else badge?.remove();
}
function setQuestionBulkBusy(catId,busy,label='處理中…'){
    const panel=document.getElementById(`qlist-${catId}`)?.parentElement; if(!panel)return;
    panel.querySelectorAll('button').forEach(btn=>{if(busy){btn.dataset.bulkPrevDisabled=btn.disabled?'1':'0';btn.disabled=true;btn.classList.add('opacity-60','cursor-wait');}else if(btn.dataset.bulkPrevDisabled==='0'){btn.disabled=false;btn.classList.remove('opacity-60','cursor-wait');delete btn.dataset.bulkPrevDisabled;}});
    const prog=document.getElementById(`qbulk-progress-${catId}`); if(prog&&busy)prog.textContent=`⏳ ${label}`;
}
function updateQuestionCacheAndPaint(catId,updates,{removeIds=[]}={}){
    let list=[...(adminQuizQuestionCache[catId]||[])];
    const byId=new Map((updates||[]).map(x=>[x.id,x]));
    list=list.filter(q=>!removeIds.includes(q.id)).map(q=>byId.has(q.id)?{...q,...byId.get(q.id)}:q);
    for(const u of (updates||[])) if(!list.some(q=>q.id===u.id)) list.push(u);
    adminQuizQuestionCache[catId]=list;
    const box=document.getElementById(`qlist-${catId}`); if(box) renderFilteredQuestionList(catId);
    const count=document.getElementById(`qcount-${catId}`); if(count)count.textContent=list.filter(q=>q.active!==false).length;
    adminUpdateQuestionSelection(catId); delete allQuizData[catId];
}
async function adminBatchQuestionPatch(catId,items,label='儲存題目'){
    const key=await getAdminKey(); if(!key)throw new Error('未輸入管理者金鑰');
    const res=await fetch('/api/quiz-questions/batch',{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({items})});
    const d=await res.json().catch(()=>({})); if(!res.ok)throw new Error(d.error||`${label}失敗`); return d;
}
async function adminSaveOneInlineQuestion(qId,catId,silent=false){
    if(questionActionBusy.has(qId))return false; questionActionBusy.add(qId); setQuestionRowBusy(qId,true,'儲存此題…');
    try{
        const key=await getAdminKey();if(!key)return false;let payload;try{payload=adminPayloadFromQuestionEditor(qId,catId);}catch(e){if(!silent)alert(e.message);throw e;}
        const res=await fetch(`/api/quiz-questions/${qId}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});const d=await res.json().catch(()=>({}));if(!res.ok){if(!silent)alert(d.error||'修改失敗');throw new Error(d.error||'修改失敗');}
        updateQuestionCacheAndPaint(catId,[{id:qId,...payload}]);
        const prog=document.getElementById(`qbulk-progress-${catId}`);if(prog&&!silent)prog.textContent='✅ 此題已儲存';return true;
    } finally {questionActionBusy.delete(qId);setQuestionRowBusy(qId,false);}
}
async function adminSaveExpandedQuestionEdits(catId){
    if(questionBulkBusy.has(catId))return; const ids=[...document.querySelectorAll(`#qlist-${catId} [id^="qedit-"]:not(.hidden)`)].map(x=>x.dataset.qid).filter(Boolean);if(!ids.length){alert('目前沒有展開中的題目。請先按「編輯已選」或「全選編輯」。');return;}if(!confirm(`確定一次儲存目前展開的 ${ids.length} 題？`))return;
    let items;try{items=ids.map(id=>({id,data:adminPayloadFromQuestionEditor(id,catId)}));}catch(e){alert(e.message);return;}
    questionBulkBusy.add(catId);setQuestionBulkBusy(catId,true,`一次儲存 ${ids.length} 題…`);ids.forEach(id=>setQuestionRowBusy(id,true,'等待批次儲存'));
    const prog=document.getElementById(`qbulk-progress-${catId}`);
    try{const d=await adminBatchQuestionPatch(catId,items,'批次儲存');updateQuestionCacheAndPaint(catId,d.updated||items.map(x=>({id:x.id,...x.data})));if(prog)prog.textContent=`✅ 已一次儲存 ${d.count||ids.length} 題，不需重新載入題庫`;}
    catch(e){if(prog)prog.textContent='⚠️ 批次儲存失敗，畫面內容已保留';alert(`批次儲存失敗：${e.message}`);}
    finally{questionBulkBusy.delete(catId);setQuestionBulkBusy(catId,false);ids.forEach(id=>setQuestionRowBusy(id,false));}
}
async function adminBulkSetQuestionTag(catId){const ids=adminSelectedQuestionIds(catId);if(!ids.length){alert('請先勾選題目');return;}const tag=prompt(`將 ${ids.length} 題的分類統一改為：`);if(tag===null)return;if(questionBulkBusy.has(catId))return;questionBulkBusy.add(catId);setQuestionBulkBusy(catId,true,`批次修改 ${ids.length} 題分類…`);try{const d=await adminBatchQuestionPatch(catId,ids.map(id=>({id,data:{tag:tag.trim()||'一般'}})),'批次分類');updateQuestionCacheAndPaint(catId,d.updated||ids.map(id=>({id,tag:tag.trim()||'一般'})));const prog=document.getElementById(`qbulk-progress-${catId}`);if(prog)prog.textContent='✅ 批次分類完成';}catch(e){alert(e.message);}finally{questionBulkBusy.delete(catId);setQuestionBulkBusy(catId,false);}}
async function adminBulkSetQuestionActive(catId,active){const ids=adminSelectedQuestionIds(catId);if(!ids.length){alert('請先勾選題目');return;}if(!confirm(`確定${active?'啟用':'停用'}已選的 ${ids.length} 題？`))return;if(questionBulkBusy.has(catId))return;questionBulkBusy.add(catId);setQuestionBulkBusy(catId,true,`${active?'啟用':'停用'} ${ids.length} 題…`);try{const d=await adminBatchQuestionPatch(catId,ids.map(id=>({id,data:{active}})),'批次狀態');updateQuestionCacheAndPaint(catId,d.updated||ids.map(id=>({id,active})));const prog=document.getElementById(`qbulk-progress-${catId}`);if(prog)prog.textContent='✅ 批次狀態完成';}catch(e){alert(e.message);}finally{questionBulkBusy.delete(catId);setQuestionBulkBusy(catId,false);}}
async function adminBulkDeleteQuestions(catId){const ids=adminSelectedQuestionIds(catId);if(!ids.length){alert('請先勾選題目');return;}if(!confirm(`確定永久刪除已選的 ${ids.length} 題？此操作無法復原。`))return;if(questionBulkBusy.has(catId))return;questionBulkBusy.add(catId);setQuestionBulkBusy(catId,true,`刪除 ${ids.length} 題…`);try{const key=await getAdminKey();if(!key)return;const r=await fetch('/api/quiz-questions/batch-delete',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({ids})});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'批次刪除失敗');updateQuestionCacheAndPaint(catId,[],{removeIds:ids});const prog=document.getElementById(`qbulk-progress-${catId}`);if(prog)prog.textContent=`✅ 已刪除 ${d.count||ids.length} 題`;}catch(e){alert(e.message);}finally{questionBulkBusy.delete(catId);setQuestionBulkBusy(catId,false);}}

async function loadQuizQuestionsIntoPanel(catId) {
    const listBox = document.getElementById(`qlist-${catId}`);
    const countEl = document.getElementById(`qcount-${catId}`);
    if (!listBox) return;
    listBox.innerHTML = '<p class="text-xs text-slate-400">載入題庫中…</p>';
    try {
        const key = await getAdminKey(); if(!key) return;
        const res = await fetch(`/api/quiz-questions/admin?category=${catId}`, {headers:{'X-Admin-Key':key}});
        const qs = await res.json();
        if (!res.ok) throw new Error(qs.error || '讀取題庫失敗');
        const activeCount=qs.filter(q=>q.active!==false).length;
        if (countEl) countEl.textContent = activeCount;
        adminQuizQuestionCache[catId]=qs;
        renderFilteredQuestionList(catId);
        adminUpdateQuestionSelection(catId);
    } catch (err) { listBox.innerHTML = `<p class="text-xs text-rose-500">❌ ${escapeHtml(err.message)}</p>`; }
}

async function adminCreateQuizCategory() {
    const key = await getAdminKey();
    if (!key) return;
    const group = document.getElementById('admin-quiz-group').value;
    const titleInput = document.getElementById('admin-new-category-title');
    const title = titleInput.value.trim();
    if (!title) { alert('請輸入頁籤名稱'); return; }
    const res = await fetch('/api/quiz-categories', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Key': key }, body: JSON.stringify({ group, area: document.getElementById('admin-quiz-area')?.value || currentTrainingArea, title }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '新增失敗'); return; }
    titleInput.value = '';
    Object.keys(dynamicCategoriesCache).filter(k=>k.endsWith(':'+group)).forEach(k=>delete dynamicCategoriesCache[k]);
    const area=document.getElementById('admin-quiz-area')?.value || currentTrainingArea;
    optimisticInsertQuizCategory({...data,questionCount:0},area,group);
    Promise.allSettled([renderAdminQuizCategories(true), document.getElementById('admin-material-group').value === group ? refreshAdminMaterialCategoryOptions() : Promise.resolve()]);
}

async function adminToggleBlindMode(catId,enabled){
    const key=await getAdminKey();if(!key)return;const btn=document.getElementById(`blind-toggle-${catId}`);if(btn){btn.disabled=true;btn.textContent='⏳ 更新盲測…';}
    try{const r=await fetch(`/api/quiz-categories/${catId}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({blindMode:!!enabled})});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'盲測設定失敗');const area=document.getElementById('admin-quiz-area')?.value||currentTrainingArea,group=document.getElementById('admin-quiz-group')?.value||currentGroupKey;adminQuizCategoriesCache.delete(adminScopeKey(area,group));await renderAdminQuizCategories(true);}catch(e){alert(e.message);if(btn){btn.disabled=false;btn.textContent='🕶️ 盲測設定';}}
}

const quizMaterialLinkState={};
async function openQuizMaterialLinker(catId){
    const qpanel=document.getElementById(`qpanel-${catId}`);qpanel?.classList.remove('hidden');const panel=document.getElementById(`qmaterial-link-${catId}`);if(!panel)return;panel.classList.remove('hidden');const list=document.getElementById(`qmaterial-list-${catId}`),status=document.getElementById(`qmaterial-status-${catId}`);if(list)list.innerHTML='<p class="text-xs text-slate-400">讀取教材中…</p>';if(status)status.textContent='';
    const key=await getAdminKey();if(!key)return;try{const r=await fetch(`/api/quiz-categories/${catId}/materials`,{headers:{'X-Admin-Key':key}});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'讀取教材失敗');quizMaterialLinkState[catId]=Array.isArray(d.items)?d.items:[];renderQuizMaterialLinker(catId);}catch(e){if(list)list.innerHTML=`<p class="text-xs text-rose-600">❌ ${escapeHtml(e.message)}</p>`;}
}
function closeQuizMaterialLinker(catId){document.getElementById(`qmaterial-link-${catId}`)?.classList.add('hidden');}
function renderQuizMaterialLinker(catId){
    const list=document.getElementById(`qmaterial-list-${catId}`);if(!list)return;const q=(document.getElementById(`qmaterial-search-${catId}`)?.value||'').trim().toLowerCase();const items=(quizMaterialLinkState[catId]||[]).filter(m=>!q||`${m.title||''} ${m.filename||''}`.toLowerCase().includes(q));
    list.innerHTML=items.length?items.map(m=>`<label class="flex items-center gap-2 rounded-lg border ${m.linked?'border-cyan-300 bg-white':'border-slate-200 bg-white/70'} px-3 py-2 text-xs"><input class="qmaterial-check-${catId}" data-mid="${escapeHtml(m.id)}" type="checkbox" ${m.linked?'checked':''}><span class="min-w-0 flex-1"><span class="font-bold text-slate-800 block truncate">${escapeHtml(m.title||m.filename)}</span><span class="text-[10px] text-slate-400">${escapeHtml(m.materialType||'standard')}${m.category&&!m.linked?' · 目前綁定其他考卷':''}</span></span></label>`).join(''):'<p class="text-xs text-slate-400 py-3">找不到符合的教材。</p>';
}
function filterQuizMaterialLinker(catId){renderQuizMaterialLinker(catId);}
async function saveQuizMaterialLinks(catId){
    const ids=[...document.querySelectorAll(`.qmaterial-check-${catId}:checked`)].map(x=>x.dataset.mid).filter(Boolean),status=document.getElementById(`qmaterial-status-${catId}`);if(status)status.textContent=`⏳ 正在儲存 ${ids.length} 份教材關聯…`;const key=await getAdminKey();if(!key)return;
    try{const r=await fetch(`/api/quiz-categories/${catId}/materials`,{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({materialIds:ids})});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'儲存關聯失敗');invalidateAdminMaterialsCache();await openQuizMaterialLinker(catId);if(status)status.textContent=`✅ 已關聯 ${d.linked||0} 份教材`;loadAiMaterialOptions(catId,true);}catch(e){if(status)status.textContent=`❌ ${e.message}`;}
}

let adminEditingExamMeta=null;
function syncExamDrawModeUI(){const limited=document.getElementById('exam-draw-limited')?.checked,quota=document.getElementById('exam-draw-quota')?.checked;document.getElementById('exam-draw-count-wrap')?.classList.toggle('hidden',!limited);document.getElementById('exam-draw-quota-wrap')?.classList.toggle('hidden',!quota);updateExamQuotaTotal();}
function updateExamQuotaTotal(){const total=['choice','multi','true_false','fill','essay','image','video'].reduce((s,k)=>s+Math.max(0,Number(document.getElementById(`exam-quota-${k}`)?.value||0)),0);const el=document.getElementById('exam-quota-total');if(el)el.textContent=`合計 ${total} 題`;return total;}
document.addEventListener('input',e=>{if(e.target?.id?.startsWith('exam-quota-'))updateExamQuotaTotal();});
async function adminEditQuizCategory(catId){return openExamSettings(catId);}
async function openExamSettings(catId){
    const key=await getAdminKey();if(!key)return;
    const group=document.getElementById('admin-quiz-group')?.value||currentGroupKey,area=document.getElementById('admin-quiz-area')?.value||currentTrainingArea;
    const status=document.getElementById('exam-settings-status');if(status)status.textContent='讀取考卷設定中…';
    await switchAdminSection('exam-settings',true); paintAdminWorkspaceNav('exams');
    try{
        const [cr,qr]=await Promise.all([fetch(`/api/quiz-categories/admin?group=${encodeURIComponent(group)}&area=${encodeURIComponent(area)}`,{headers:{'X-Admin-Key':key}}),fetch(`/api/courses/admin?group=${encodeURIComponent(group)}&area=${encodeURIComponent(area)}`,{headers:{'X-Admin-Key':key}})]);
        const cats=await cr.json().catch(()=>[]),courses=await qr.json().catch(()=>[]);const c=(cats||[]).find(x=>x.id===catId);if(!c)throw new Error('找不到此考卷');adminEditingExamMeta={...c,group,area};
        document.getElementById('exam-settings-id').value=catId;document.getElementById('exam-settings-heading').textContent=`📋 ${c.title||'考卷'}｜設定`;document.getElementById('exam-settings-title').value=c.title||'';document.getElementById('exam-settings-desc').value=c.desc||'';document.getElementById('exam-settings-audience').value=c.audience||'';document.getElementById('exam-settings-passing-score').value=Number(c.passingScore||80);document.getElementById('exam-settings-blind').checked=!!c.blindMode;
        const courseSel=document.getElementById('exam-settings-course');courseSel.innerHTML='<option value="">通用考卷（未指定課程）</option>'+((courses||[]).map(x=>`<option value="${escapeHtml(x.id)}">${escapeHtml(x.title)}</option>`).join(''));courseSel.value=c.courseId||'';
        const draw=Math.max(0,Number(c.drawCount||0)),rules=c.drawRules||{},isQuota=rules.mode==='type_quota';document.getElementById(isQuota?'exam-draw-quota':(draw>0?'exam-draw-limited':'exam-draw-all')).checked=true;document.getElementById('exam-settings-draw-count').value=draw>0?draw:'';for(const k of ['choice','multi','true_false','fill','essay','image','video']){const el=document.getElementById(`exam-quota-${k}`);if(el)el.value=Math.max(0,Number(rules.quotas?.[k]||0));}syncExamDrawModeUI();document.getElementById('exam-settings-question-summary').textContent=`目前題庫：${Number(c.questionCount||0)} 題；${examDrawLabel(c)}`;document.getElementById('exam-reviewer-name').value=c.reviewerName||readLocalMemory(EVALUATOR_NAME_MEMORY_KEY)||'';updateExamWorkflowUI(c);
        if(status)status.textContent='';
    }catch(e){if(status)status.textContent='❌ '+e.message;}
}
async function saveExamSettings(){
    const key=await getAdminKey();if(!key)return;const catId=document.getElementById('exam-settings-id').value;if(!catId)return;const status=document.getElementById('exam-settings-status'),btn=document.getElementById('exam-settings-save-btn');const title=document.getElementById('exam-settings-title').value.trim();if(!title){status.textContent='❌ 請輸入考卷名稱';return;}const limited=document.getElementById('exam-draw-limited').checked,quotaMode=document.getElementById('exam-draw-quota').checked;const drawCount=limited?Math.max(1,parseInt(document.getElementById('exam-settings-draw-count').value||'1',10)||1):0;const quotas=Object.fromEntries(['choice','multi','true_false','fill','essay','image','video'].map(k=>[k,Math.max(0,parseInt(document.getElementById(`exam-quota-${k}`)?.value||'0',10)||0)]));if(quotaMode&&Object.values(quotas).reduce((a,b)=>a+b,0)<=0){status.textContent='❌ 題型配額至少要設定 1 題';return;}const drawRules=quotaMode?{mode:'type_quota',quotas}:{};const passingScore=Math.max(1,Math.min(100,parseInt(document.getElementById('exam-settings-passing-score').value||'80',10)||80));const payload={title,desc:document.getElementById('exam-settings-desc').value.trim(),audience:document.getElementById('exam-settings-audience').value.trim(),courseId:document.getElementById('exam-settings-course').value||'',drawCount,drawRules,passingScore,active:false,reviewStatus:'draft',reviewerName:'',reviewedAt:'',publishedAt:'',blindMode:document.getElementById('exam-settings-blind').checked};
    try{btn.disabled=true;status.textContent='⏳ 儲存設定中…';const res=await fetch(`/api/quiz-categories/${catId}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)}),data=await res.json().catch(()=>({}));if(!res.ok)throw new Error(data.error||'修改失敗');adminEditingExamMeta={...(adminEditingExamMeta||{}),...payload,reviewStatus:'draft',active:false};Object.keys(dynamicCategoriesCache).filter(k=>k.endsWith(':'+(adminEditingExamMeta?.group||currentGroupKey))).forEach(k=>delete dynamicCategoriesCache[k]);delete allQuizData[catId];clearExamDraft(catId);adminQuizCategoriesCache.clear();status.textContent='✅ 設定已儲存；因內容已變更，考卷回到「待審核」狀態。';updateExamWorkflowUI(adminEditingExamMeta);}catch(e){status.textContent='❌ '+e.message;}finally{btn.disabled=false;}
}

function updateExamWorkflowUI(meta){meta=meta||adminEditingExamMeta||{};const st=document.getElementById('exam-workflow-status'),steps=document.querySelectorAll('#exam-workflow-steps [data-stage]');let current=meta.active?'publish':(meta.reviewStatus==='approved'?'review':'settings');steps.forEach(el=>{const order={select:1,method:2,settings:3,review:4,publish:5};el.classList.toggle('is-done',order[el.dataset.stage]<(order[current]||3));el.classList.toggle('is-current',el.dataset.stage===current);});if(st)st.textContent=meta.active?`🚀 已發布${meta.publishedAt?'・'+meta.publishedAt:''}${meta.publicationHash?'・快照 '+meta.publicationHash.slice(0,10):''}`:(meta.reviewStatus==='approved'?`✅ 已由 ${meta.reviewerName||'審核者'} 審核，待發布`:'📝 草稿／設定中，完成預覽後請審核');const pb=document.getElementById('exam-publish-btn');if(pb)pb.disabled=meta.reviewStatus!=='approved'||!!meta.active;}

async function reviewCurrentExam(){const catId=document.getElementById('exam-settings-id').value,reviewerName=document.getElementById('exam-reviewer-name').value.trim(),status=document.getElementById('exam-settings-status');if(!catId)return;if(!reviewerName){status.textContent='❌ 請填寫審核者姓名';return;}await previewCurrentExam();const key=await getAdminKey();if(!key)return;try{status.textContent='⏳ 正在檢查題目完整性並送出審核…';const r=await fetch(`/api/quiz-categories/${catId}/review`,{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({reviewerName})}),d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.issues?.length?`${d.error}：${d.issues.join('、')}`:(d.error||'審核失敗'));adminEditingExamMeta={...(adminEditingExamMeta||{}),reviewStatus:'approved',reviewerName,reviewedAt:d.reviewedAt,active:false};status.textContent=`✅ 審核完成：${reviewerName}；現在可發布考卷。`;updateExamWorkflowUI(adminEditingExamMeta);adminQuizCategoriesCache.clear();}catch(e){status.textContent='❌ '+e.message;}}

async function publishCurrentExam(){const catId=document.getElementById('exam-settings-id').value,status=document.getElementById('exam-settings-status');if(!catId)return;const key=await getAdminKey();if(!key)return;try{status.textContent='⏳ 正在建立不可漂移發布快照並發布…';const r=await fetch(`/api/quiz-categories/${catId}/publish`,{method:'POST',headers:{'X-Admin-Key':key}}),d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'發布失敗');adminEditingExamMeta={...(adminEditingExamMeta||{}),active:true,publishedAt:d.publishedAt,reviewStatus:'approved',publicationId:d.publicationId||'',publicationHash:d.publicationHash||''};status.textContent=`🚀 考卷已發布；已保存 ${Number(d.snapshotQuestionCount||0)} 題發布快照${d.publicationHash?'（'+d.publicationHash.slice(0,10)+'…）':''}。`;updateExamWorkflowUI(adminEditingExamMeta);adminQuizCategoriesCache.clear();Object.keys(dynamicCategoriesCache).forEach(k=>delete dynamicCategoriesCache[k]);}catch(e){status.textContent='❌ '+e.message;}}

async function adminDeleteQuizCategory(catId) {
    if (!confirm('確定刪除此考題頁籤？頁籤內所有題目也會一併刪除，此操作無法復原。')) return;
    const key = await getAdminKey();
    if (!key) return;
    const group = document.getElementById('admin-quiz-group').value;
    const res = await fetch(`/api/quiz-categories/${catId}`, { method: 'DELETE', headers: { 'X-Admin-Key': key } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '刪除失敗'); return; }
    Object.keys(dynamicCategoriesCache).filter(k=>k.endsWith(':'+group)).forEach(k=>delete dynamicCategoriesCache[k]);
    delete allQuizData[catId];
    adminQuizCategoriesCache.delete(adminScopeKey(document.getElementById('admin-quiz-area')?.value || currentTrainingArea,group));
    await renderAdminQuizCategories(true);
    await refreshAdminMaterialCategoryOptions();
}

async function adminImportQuizUrl(catId) {
    const key = await getAdminKey(); if (!key) return;
    const el=document.getElementById(`qimport-${catId}`); const url=el?.value.trim();
    if(!url){alert('請貼上 JSON 或 CSV 題庫公開連結');return;}
    const res=await fetch('/api/quiz-questions/import-url',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({quizCategoryId:catId,url})});
    const data=await res.json().catch(()=>({})); if(!res.ok){alert(data.error||'匯入失敗');return;}
    alert(`成功匯入 ${data.imported} 題${data.errors?.length ? `；另有 ${data.errors.length} 筆略過` : ''}`); if(el)el.value='';
    delete allQuizData[catId]; await loadQuizQuestionsIntoPanel(catId);
}

async function adminAddQuizQuestion(catId) {
    const key=await getAdminKey();if(!key)return;
    const question=document.getElementById(`qform-${catId}-question`).value.trim();
    const rawType=document.getElementById(`qform-${catId}-type`).value;
    const isVideo=rawType.startsWith('video_');
    const questionType=isVideo?rawType.slice(6):rawType;
    const difficulty=document.getElementById(`qform-${catId}-difficulty`)?.value||'standard';
    if(!question){alert('請輸入題目內容');return;}
    let imageUrl='';const imageFile=document.getElementById(`qform-${catId}-image`)?.files?.[0];if(imageFile){const fd=new FormData();fd.append('file',imageFile);const ir=await fetch('/api/quiz-question-images',{method:'POST',headers:{'X-Admin-Key':key},body:fd});const idata=await ir.json();if(!ir.ok){alert(idata.error||'圖片上傳失敗');return;}imageUrl=idata.url;}
    const options=[0,1,2,3].map(i=>document.getElementById(`qform-${catId}-opt${i}`)?.value.trim()||'');const answerConfig={};
    if(questionType==='multi')answerConfig.correctIndices=[0,1,2,3].filter(i=>document.getElementById(`qform-${catId}-multi${i}`)?.checked);
    if(questionType==='fill')answerConfig.acceptedAnswers=(document.getElementById(`qform-${catId}-fill-answers`)?.value||'').split('|').map(x=>x.trim()).filter(Boolean);
    if(isVideo){answerConfig.mediaUrl=document.getElementById(`qform-${catId}-media-url`)?.value.trim()||'';answerConfig.pauseAt=Number(document.getElementById(`qform-${catId}-pause-at`)?.value||0);if(!answerConfig.mediaUrl){alert('影片題請填入影片教材播放網址');return;}}
    const needsOptions=['choice','multi','image','true_false'].includes(questionType);
    const payload={quizCategoryId:catId,question,questionType,difficulty,imageUrl,options:questionType==='true_false'?['是','否']:(needsOptions?options:[]),correct:questionType==='true_false'?Number(document.getElementById(`qform-${catId}-truefalse-correct`)?.value||0):Number(document.getElementById(`qform-${catId}-correct`)?.value||0),answerConfig,tag:document.getElementById(`qform-${catId}-tag`).value.trim(),explanation:document.getElementById(`qform-${catId}-explain`).value.trim()};
    const res=await fetch('/api/quiz-questions',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});const data=await res.json().catch(()=>({}));if(!res.ok){alert(data.error||'新增失敗');return;}
    ['question','opt0','opt1','opt2','opt3','tag','explain','fill-answers','media-url','pause-at'].forEach(f=>{const el=document.getElementById(`qform-${catId}-${f}`);if(el)el.value='';});[0,1,2,3].forEach(i=>{const el=document.getElementById(`qform-${catId}-multi${i}`);if(el)el.checked=false;});if(document.getElementById(`qform-${catId}-image`))document.getElementById(`qform-${catId}-image`).value='';await loadQuizQuestionsIntoPanel(catId);delete allQuizData[catId];
}

async function adminEditQuizQuestion(qId, catId) {
    const key = await getAdminKey(); if (!key) return;
    const res0 = await fetch(`/api/quiz-questions/admin?category=${catId}`, {headers:{'X-Admin-Key':key}});
    const qs = await res0.json().catch(() => []); const q = (qs || []).find(x => x.id === qId); if (!q) return;
    const type=q.questionType||'choice';
    const question = prompt('題目內容：', q.question || ''); if (question === null) return;
    const tag = prompt('題目分類標籤：', q.tag || ''); if (tag === null) return;
    const explanation = prompt(type==='essay' ? '評分參考 / 標準答案重點：' : '詳解 / 答案依據：', q.explanation || ''); if (explanation === null) return;
    const payload={question, tag, explanation, questionType:type, imageUrl:q.imageUrl||'', answerConfig:{...(q.answerConfig||{})}};
    if(type==='essay'){payload.options=[];payload.correct=0;}
    else if(type==='fill'){
        const prev=(q.answerConfig?.acceptedAnswers||[]).join(' | ');
        const raw=prompt('可接受答案（多個答案請用 | 分隔）：',prev); if(raw===null)return;
        const arr=raw.split('|').map(x=>x.trim()).filter(Boolean);if(!arr.length){alert('至少需要一個可接受答案');return;}
        payload.options=[];payload.correct=0;payload.answerConfig={...(q.answerConfig||{}),acceptedAnswers:arr,caseSensitive:false};
    }else{
        const opts=[];const optCount=Math.max(4,(q.options||[]).length);
        for(let i=0;i<optCount;i++){const v=prompt(`選項 ${String.fromCharCode(65+i)}（留白代表不使用）：`,(q.options||[])[i]||'');if(v===null)return;if(v.trim())opts.push(v.trim());}
        if(opts.length<2){alert('至少需要 2 個選項');return;} payload.options=opts;
        if(type==='multi'){
            const prev=(q.answerConfig?.correctIndices||[]).map(i=>'ABCDEF'[Number(i)]).filter(Boolean).join(',');
            const raw=prompt(`多選正確答案（例如 A,C；可複選，選項上限 ${opts.length}）：`,prev);if(raw===null)return;
            const indices=[...new Set((raw.toUpperCase().match(/[A-F]/g)||[]).map(x=>'ABCDEF'.indexOf(x)).filter(i=>i>=0&&i<opts.length))];
            if(!indices.length){alert('多選題至少設定一個正確選項');return;}payload.correct=indices[0];payload.answerConfig={...(q.answerConfig||{}),correctIndices:indices};
        }else{
            const correctStr=prompt(`正確答案是第幾個選項？（輸入 1 ~ ${opts.length}）`,String((q.correct||0)+1));if(correctStr===null)return;
            payload.correct=Math.max(0,Math.min(opts.length-1,(parseInt(correctStr,10)||1)-1));
        }
        if(type==='video'||q.answerConfig?.mediaUrl){
            const media=prompt('影片網址 / 教材播放網址：',q.answerConfig?.mediaUrl||'');if(media===null)return;
            const sec=prompt('建議觀察時間點（秒）：',String(q.answerConfig?.pauseAt||0));if(sec===null)return;
            payload.answerConfig={...(payload.answerConfig||{}),mediaUrl:media.trim(),pauseAt:Math.max(0,Number(sec)||0)};
        }
    }
    const res=await fetch(`/api/quiz-questions/${qId}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});
    const data=await res.json().catch(()=>({}));if(!res.ok){alert(data.error||'修改失敗');return;}await loadQuizQuestionsIntoPanel(catId);delete allQuizData[catId];
}

async function adminToggleQuizQuestion(qId, catId, active) {
    if(questionActionBusy.has(qId))return;questionActionBusy.add(qId);setQuestionRowBusy(qId,true,active?'啟用中…':'停用中…');
    try{const key=await getAdminKey();if(!key)return;const res=await fetch(`/api/quiz-questions/${qId}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})});const data=await res.json().catch(()=>({}));if(!res.ok)throw new Error(data.error||'更新失敗');updateQuestionCacheAndPaint(catId,[{id:qId,active}]);}
    catch(e){alert(e.message);}finally{questionActionBusy.delete(qId);setQuestionRowBusy(qId,false);}
}
async function adminDeleteQuizQuestion(qId, catId) {
    if (!confirm('確定刪除此題目？此操作無法復原。')) return;if(questionActionBusy.has(qId))return;questionActionBusy.add(qId);setQuestionRowBusy(qId,true,'刪除中…');
    try{const key=await getAdminKey();if(!key)return;const res=await fetch(`/api/quiz-questions/${qId}`,{method:'DELETE',headers:{'X-Admin-Key':key}});const data=await res.json().catch(()=>({}));if(!res.ok)throw new Error(data.error||'刪除失敗');updateQuestionCacheAndPaint(catId,[],{removeIds:[qId]});}
    catch(e){alert(e.message);}finally{questionActionBusy.delete(qId);setQuestionRowBusy(qId,false);}
}


// ==================================================================

// ==================================================================
// 管理者後台：各組別 Word 匯出範本 (doc_templates) 管理
// 六組皆可由後台上傳 Word 匯出範本；生化組也納入統一管理。
// ==================================================================
let cachedDocTemplatesMeta = [];
let pendingDocTemplateUploadGroup = null;

async function renderAdminDocTemplates() {
    const box = document.getElementById('admin-doc-templates-list');
    if (!box) return;
    box.innerHTML = '<p class="text-xs text-slate-400">讀取範本設定中…</p>';
    try {
        const res = await fetch('/api/doc-templates');
        const list = await res.json();
        cachedDocTemplatesMeta = list;
        const rows = list;
        box.innerHTML = rows.map(g => `
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border border-amber-200 rounded-xl p-2.5 bg-white">
                <div class="min-w-0">
                    <span class="font-bold text-sm text-slate-800">${escapeHtml(g.label)}</span>
                    ${g.exists
                        ? `<span class="text-xs text-emerald-700 ml-2">✅ 已設定：${escapeHtml(g.filename)}（${escapeHtml(g.uploadedAt)}）</span><span class="text-[10px] text-slate-400 ml-2">${g.storageBackend === 'mega' ? '🟣 MEGA' : (g.storageBackend === 'oci' ? '🔴 Oracle' : (g.storageBackend === 'gdrive' ? '🟢 Google Drive' : (g.storageBackend === 'r2' ? '☁️ R2' : '💾 本機')))}</span>`
                        : `<span class="text-xs text-slate-400 ml-2">尚未上傳範本</span>`}
                </div>
                <div class="flex gap-2 shrink-0">
                    <button onclick="adminTriggerDocTemplateUpload('${g.group}')" class="text-xs bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded-lg">⬆️ ${g.exists ? '重新上傳' : '上傳範本'}</button>
                    ${g.exists ? `<a href="/api/doc-templates/${g.group}/download" target="_blank" class="text-xs bg-white border border-amber-300 hover:bg-amber-50 text-amber-800 px-3 py-1.5 rounded-lg">⬇️ 下載目前範本</a><button onclick="adminDeleteDocTemplate('${g.group}')" class="text-[11px] bg-white border border-slate-200 hover:border-rose-200 text-slate-500 hover:text-rose-700 px-2.5 py-1.5 rounded-lg">更多：刪除</button>` : ''}
                </div>
            </div>`).join('');
    } catch (err) {
        box.innerHTML = `<p class="text-xs text-rose-500">❌ ${escapeHtml(err.message)}</p>`;
    }
}

function adminTriggerDocTemplateUpload(groupKey) {
    pendingDocTemplateUploadGroup = groupKey;
    document.getElementById('admin-doc-template-upload-input').click();
}

document.getElementById('admin-doc-template-upload-input').addEventListener('change', async function (e) {
    const file = e.target.files[0];
    e.target.value = '';
    const groupKey = pendingDocTemplateUploadGroup;
    pendingDocTemplateUploadGroup = null;
    if (!file || !groupKey) return;
    const key = await getAdminKey();
    if (!key) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch(`/api/doc-templates/${groupKey}`, { method: 'POST', headers: { 'X-Admin-Key': key }, body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || '上傳失敗');
        alert(`✅ Word 範本格式檢查通過並已上傳（${Math.round((data.validation?.sizeBytes||0)/1024)} KB）`);
        await renderAdminDocTemplates();
    } catch (err) {
        alert(`❌ ${err.message}`);
    }
});

async function adminDeleteDocTemplate(groupKey) {
    if (!confirm('確定刪除此組別的 Word 匯出範本？')) return;
    const key = await getAdminKey();
    if (!key) return;
    const res = await fetch(`/api/doc-templates/${groupKey}`, { method: 'DELETE', headers: { 'X-Admin-Key': key } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '刪除失敗'); return; }
    await renderAdminDocTemplates();
}

function updateAdminMaterialTypeFields(){const type=document.getElementById('admin-material-type')?.value||'standard';document.getElementById('admin-atlas-fields')?.classList.toggle('hidden',type!=='atlas');}

let materialJobsRefreshTimer=null;
function materialJobStatusLabel(status){return ({queued:'等待處理',retry_wait:'等待重試',processing:'背景處理中',completed:'已完成',failed:'失敗',cancelled:'已取消'})[status]||status||'未知';}
function materialJobStatusClass(status){return status==='completed'?'text-emerald-700 bg-emerald-50 border-emerald-200':status==='failed'?'text-rose-700 bg-rose-50 border-rose-200':status==='processing'?'text-sky-700 bg-sky-50 border-sky-200':status==='retry_wait'?'text-amber-700 bg-amber-50 border-amber-200':'text-slate-600 bg-slate-50 border-slate-200';}
function scheduleMaterialJobsRefresh(active){
    if(materialJobsRefreshTimer){clearTimeout(materialJobsRefreshTimer);materialJobsRefreshTimer=null;}
    if(active)materialJobsRefreshTimer=setTimeout(()=>renderMaterialJobs(false),4000);
}
async function renderMaterialJobs(force=false){
    const host=document.getElementById('admin-material-jobs-list');if(!host)return;
    const key=await getAdminKey();if(!key)return;
    try{
        const r=await fetch(`/api/material-jobs?limit=20${force?'&refresh=1':''}`,{headers:{'X-Admin-Key':key},cache:'no-store'}),d=await r.json().catch(()=>({}));
        if(!r.ok)throw new Error(d.error||'背景工作讀取失敗');
        const jobs=d.jobs||[];
        if(!jobs.length){host.innerHTML='<p class="text-xs text-slate-400">目前沒有背景教材工作。</p>';scheduleMaterialJobsRefresh(false);return;}
        host.innerHTML=jobs.map(j=>{const pct=Math.max(0,Math.min(100,Number(j.progress||0))), retry=j.status==='failed'&&j.attempts>=j.maxAttempts;return `<div class="rounded-xl border bg-white p-3"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-2 flex-wrap"><span class="text-[10px] border rounded-full px-2 py-0.5 font-bold ${materialJobStatusClass(j.status)}">${escapeHtml(materialJobStatusLabel(j.status))}</span><b class="text-xs text-slate-800 truncate">${escapeHtml(j.result?.title||j.title||j.result?.filename||j.originalName||j.id)}</b><span class="text-[10px] text-slate-400">${formatFileBytes(j.sourceBytes||0)}</span></div><p class="text-[11px] text-slate-600 mt-1">${escapeHtml(j.stage||'')}｜${escapeHtml(j.detail||'')}</p>${j.error?`<p class="text-[10px] text-rose-600 mt-1">${escapeHtml(j.error)}</p>`:''}</div><div class="flex gap-1 shrink-0">${retry?`<button onclick="retryMaterialJob('${escapeHtml(j.id)}')" class="text-[10px] px-2 py-1 rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold">重新處理</button>`:''}${['queued','retry_wait'].includes(j.status)?`<button onclick="cancelMaterialJob('${escapeHtml(j.id)}')" class="text-[10px] px-2 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600">取消</button>`:''}</div></div><div class="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden"><div class="h-full bg-sky-500 transition-all" style="width:${j.status==='completed'?100:pct}%"></div></div><div class="mt-1 text-[10px] text-slate-400">工作 ${escapeHtml(j.id)} · 第 ${Number(j.attempts||0)}/${Number(j.maxAttempts||3)} 次${j.materialId?` · 教材 ${escapeHtml(j.materialId)}`:''}</div></div>`}).join('');
        scheduleMaterialJobsRefresh(jobs.some(j=>['queued','retry_wait','processing'].includes(j.status)));
    }catch(err){host.innerHTML=`<p class="text-xs text-rose-600">❌ ${escapeHtml(err.message)}</p>`;scheduleMaterialJobsRefresh(false);}
}
async function retryMaterialJob(id){const key=await getAdminKey();if(!key)return;const r=await fetch(`/api/material-jobs/${encodeURIComponent(id)}/retry`,{method:'POST',headers:{'X-Admin-Key':key}}),d=await r.json().catch(()=>({}));if(!r.ok){alert(d.error||'重新處理失敗');return;}await renderMaterialJobs(true);}
async function cancelMaterialJob(id){if(!confirm('確定取消尚未開始的教材背景工作？'))return;const key=await getAdminKey();if(!key)return;const r=await fetch(`/api/material-jobs/${encodeURIComponent(id)}/cancel`,{method:'POST',headers:{'X-Admin-Key':key}}),d=await r.json().catch(()=>({}));if(!r.ok){alert(d.error||'取消失敗');return;}await renderMaterialJobs(true);}
function uploadAdminMaterialRequest(fd,progressId,fileName,key,status){
    return new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();
        xhr.open('POST','/api/material-jobs/upload',true);xhr.setRequestHeader('X-Admin-Key',key);xhr.timeout=20*60*1000;
        xhr.upload.onprogress=e=>{if(e.lengthComputable&&status){const pct=Math.round(e.loaded/e.total*100);status.innerHTML=`⬆️ ${escapeHtml(fileName)}｜安全接收 ${pct}%<span class="block text-[11px] text-slate-500 mt-1">${(e.loaded/1024/1024).toFixed(1)} / ${(e.total/1024/1024).toFixed(1)} MB；接收後會立刻排入背景佇列，不再占住 Web worker。</span>`;}};
        xhr.onload=()=>{let d={};try{d=JSON.parse(xhr.responseText||'{}')}catch(_e){};if(xhr.status>=200&&xhr.status<300)resolve(d);else reject(new Error(d.error||`HTTP ${xhr.status}`));};
        xhr.onerror=()=>reject(new Error(`${fileName} 網路上傳失敗`));
        xhr.ontimeout=()=>reject(new Error(`${fileName} 傳送到伺服器逾時`));
        xhr.send(fd);
    });
}

async function adminUploadMaterials() {
    const input=document.getElementById('admin-pptx-upload-input'),files=Array.from(input?.files||[]);if(!files.length){alert('請先選擇要上傳的教材檔案。');return;}
    const key=await getAdminKey();if(!key)return;
    const title=document.getElementById('admin-material-title').value.trim(),desc=document.getElementById('admin-material-desc').value.trim(),group=document.getElementById('admin-material-group').value,category=document.getElementById('admin-material-category').value,status=document.getElementById('admin-upload-status'),btn=document.getElementById('admin-upload-btn');
    btn.disabled=true;let queued=0,failed=[];const jobIds=[];status.innerHTML=`⏳ 準備安全接收 ${files.length} 份教材…`;
    for(let n=0;n<files.length;n++){
        const file=files[n],progressId=`manual-${Date.now()}-${n}-${Math.random().toString(36).slice(2,8)}`;
        status.innerHTML=`⏳ ${n+1}/${files.length} 接收「${escapeHtml(file.name)}」<span class="block text-[11px] text-slate-500 mt-1">只等待檔案傳到 Render；轉檔、壓縮、MEGA 上傳會在背景繼續。</span>`;
        const fd=new FormData();fd.append('file',file);fd.append('title',title);fd.append('desc',desc);fd.append('category',category);fd.append('group',group);fd.append('area',document.getElementById('admin-material-area')?.value||currentTrainingArea);fd.append('courseId',document.getElementById('admin-material-course')?.value||'');fd.append('materialType',document.getElementById('admin-material-type')?.value||'standard');fd.append('progressId',progressId);fd.append('atlasCategory',document.getElementById('admin-atlas-category')?.value||'');fd.append('atlasMagnification',document.getElementById('admin-atlas-magnification')?.value||'');fd.append('atlasInterpretation',document.getElementById('admin-atlas-interpretation')?.value||'');fd.append('atlasClinical',document.getElementById('admin-atlas-clinical')?.value||'');fd.append('atlasDifferential',document.getElementById('admin-atlas-differential')?.value||'');fd.append('atlasNormality',document.getElementById('admin-atlas-normality')?.value||'');fd.append('atlasTags',document.getElementById('admin-atlas-tags')?.value||'');
        try{const data=await uploadAdminMaterialRequest(fd,progressId,file.name,key,status);queued++;if(data.jobId)jobIds.push(data.jobId);status.innerHTML=`✅ ${n+1}/${files.length}「${escapeHtml(file.name)}」已加入背景佇列<span class="block text-[11px] mt-1">${escapeHtml(data.jobId||'')}｜現在可切換頁面或關閉後台視窗，工作會繼續。</span>`;}
        catch(err){failed.push({name:file.name,error:err.message});status.innerHTML=`❌ ${escapeHtml(file.name)}：${escapeHtml(err.message)}<span class="block text-[11px] mt-1">其他檔案會繼續接收。</span>`;}
    }
    if(failed.length){status.innerHTML=`⚠️ 已排入 ${queued}/${files.length} 份；${failed.length} 份接收失敗。<details class="mt-1"><summary class="cursor-pointer font-bold">查看失敗原因</summary><div class="mt-1 space-y-1">${failed.map(x=>`<div>• ${escapeHtml(x.name)}：${escapeHtml(x.error)}</div>`).join('')}</div></details>`;}
    else status.innerHTML=`✅ ${queued} 份教材已安全接收並排入背景工作。你可以離開此頁；完成後會自動出現在教材清單。`;
    input.value='';document.getElementById('admin-material-title').value='';document.getElementById('admin-material-desc').value='';['admin-atlas-category','admin-atlas-magnification','admin-atlas-interpretation','admin-atlas-clinical','admin-atlas-differential','admin-atlas-tags'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});btn.disabled=false;await renderMaterialJobs(true);
}
async function editAdminMaterial(id) {
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
    let atlasMeta={...(m.atlasMeta||{})};
    if((m.materialType||'standard')==='atlas'){
        const fields=[['category','圖譜分類'],['magnification','倍率 / 染色'],['interpretation','判讀重點'],['clinical','臨床意義'],['differential','常見鑑別點']];
        fields.push(['normality','正／異常標記'],['tags','標籤（逗號分隔）']);for(const [k,label] of fields){const v=prompt(`${label}：`,atlasMeta[k]||'');if(v===null)return;atlasMeta[k]=v.trim();}
    }
    const key = await getAdminKey();
    const res = await fetch(`/api/slides/${id}`, { method: 'PATCH', headers: {'Content-Type':'application/json','X-Admin-Key':key}, body: JSON.stringify({title, desc, category, group, materialType:m.materialType||'standard', atlasMeta}) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '修改失敗'); return; }
    invalidateAdminMaterialsCache(); await renderAdminMaterials(true); await renderAdminCourseMaterialHub(true); await renderSlidesGrid();
}

async function toggleAdminMaterial(id, active) {
    const key = await getAdminKey();
    const res = await fetch(`/api/slides/${id}`, { method:'PATCH', headers:{'Content-Type':'application/json','X-Admin-Key':key}, body:JSON.stringify({active}) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '更新失敗'); return; }
    invalidateAdminMaterialsCache(); await renderAdminMaterials(true); await renderAdminCourseMaterialHub(true); await renderSlidesGrid();
}

async function deleteAdminMaterial(id) {
    if (!confirm('確定刪除這份教材嗎？教材檔案與轉換圖片都會刪除，此操作無法復原。')) return;
    const key = await getAdminKey();
    const res = await fetch(`/api/slides/${id}`, { method:'DELETE', headers:{'X-Admin-Key':key} });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '刪除失敗'); return; }
    invalidateAdminMaterialsCache(); await renderAdminMaterials(true); await renderAdminCourseMaterialHub(true); await renderSlidesGrid();
}

let adminWorkspace = 'course-materials';
let adminQuizWorkspaceMode = 'questions';
let adminResultWorkspaceMode = 'results';
let teacherWorkspaceMode = 'scoring';

function normalizeAdminWorkspace(name){
    if(name==='courses'||name==='materials') return 'course-materials';
    if(name==='scoring'||name==='pgy') return 'teacher';
    return name;
}
function paintAdminWorkspaceNav(name){
    name=normalizeAdminWorkspace(name);
    const names=['course-materials','exams','results','people','questions','teacher','word','system'];
    names.forEach(n=>{const b=document.getElementById(`admin-nav-${n}`);if(!b)return;b.className=n===name?'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-teal-700 text-white shadow-sm':'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';});
}

function syncAdminSectionChrome(name){
    const actions=document.getElementById('exam-settings-actions');
    if(actions) actions.classList.toggle('hidden',name!=='exam-settings');
    const teacherNav=document.getElementById('admin-teacher-subnav');
    if(teacherNav) teacherNav.classList.toggle('hidden',adminWorkspace!=='teacher');
    const modal=document.getElementById('admin-modal');
    if(modal){modal.dataset.workspace=adminWorkspace||'';modal.dataset.section=name||'';}
}

async function switchAdminSection(name, force=false) {
    const names=['content','quiz','word','pgy','results','exam-settings','people','system'];
    names.forEach(n=>document.getElementById(`admin-section-${n}`)?.classList.toggle('hidden', n!==name));
    syncAdminSectionChrome(name);
    if(name==='exam-settings'||name==='people'||name==='system') return;
    if (!force && adminSectionLoaded[name]) return;
    adminSectionLoaded[name] = true;
    if(name==='content') {
        await Promise.allSettled([refreshAdminMaterialCategoryOptions(),renderAdminCourses(),renderAdminMaterials(force)]);
        await renderAdminCourseMaterialHub(force);
    }
    if(name==='quiz') await renderAdminQuizCategories(force);
    if(name==='word') await renderAdminDocTemplates();
    if(name==='pgy') await Promise.allSettled([renderAdminPgyTemplates(),renderAdminPgyAssessments()]);
    if(name==='results') await renderAdminTable();
}

async function openAdminWorkspace(name){await toggleAdminModal(true);await switchAdminWorkspace(name,true);}
function openTeacherAssessment(){return openAdminWorkspace('teacher');}

function paintTeacherMode(){
    const a=document.getElementById('teacher-mode-scoring'),b=document.getElementById('teacher-mode-pgy');
    if(a)a.className=teacherWorkspaceMode==='scoring'?'px-3 py-1.5 rounded-lg bg-indigo-700 text-white text-xs font-bold':'px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-xs font-bold';
    if(b)b.className=teacherWorkspaceMode==='pgy'?'px-3 py-1.5 rounded-lg bg-indigo-700 text-white text-xs font-bold':'px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-xs font-bold';
}
async function switchTeacherMode(mode){
    teacherWorkspaceMode=mode==='pgy'?'pgy':'scoring';
    paintTeacherMode();
    if(teacherWorkspaceMode==='pgy'){await switchAdminSection('pgy',true);return;}
    adminResultWorkspaceMode='scoring';await switchAdminSection('results',true);updateResultsWorkspacePresentation();
}

async function switchAdminWorkspace(name, force=false){
    const requested=name; name=normalizeAdminWorkspace(name);
    adminWorkspace=name; paintAdminWorkspaceNav(name);
    if(name==='course-materials'){
        await switchAdminSection('content',force);
        const courses=document.getElementById('admin-course-workspace'), materials=document.getElementById('admin-material-workspace'), advanced=document.getElementById('admin-material-advanced');
        courses?.classList.remove('hidden'); materials?.classList.remove('hidden'); advanced?.classList.remove('hidden');
        setTimeout(()=>{renderStorageStatus(false);renderMaterialJobs(false);},0);
        return;
    }
    if(name==='questions'||name==='exams'){
        adminQuizWorkspaceMode=name; await switchAdminSection('quiz',force); updateQuizWorkspacePresentation(); return;
    }
    if(name==='teacher'){
        teacherWorkspaceMode=requested==='pgy'?'pgy':'scoring';paintTeacherMode();await switchTeacherMode(teacherWorkspaceMode);return;
    }
    if(name==='results'){
        adminResultWorkspaceMode='results'; await switchAdminSection('results',true); updateResultsWorkspacePresentation(); return;
    }
    if(name==='word'){await switchAdminSection('word',force);return;}
    if(name==='people'){await switchAdminSection('people',true);await renderAdminPeople(force);return;}
    if(name==='system'){await switchAdminSection('system',true);await Promise.all([renderAdminSystemStatus(force),renderAdminAnnouncements()]);return;}
}

function updateQuizWorkspacePresentation(){
    const title=document.querySelector('#admin-quiz-workspace h4'); const desc=document.querySelector('#admin-quiz-workspace h4 + p');
    if(title) title.textContent=adminQuizWorkspaceMode==='exams'?'📋 考卷管理':'📝 題庫管理與 AI 出題';
    if(desc) desc.textContent=adminQuizWorkspaceMode==='exams'?'建立、啟用、停用與設定考卷；點「考卷設定」進入完整設定頁。':'選擇考卷後管理正式題庫、快速編輯、批次操作與 AI 候選題。';
    document.querySelectorAll('[data-admin-role="questions-action"]').forEach(x=>x.classList.toggle('hidden',adminQuizWorkspaceMode!=='questions'));
    document.querySelectorAll('[data-admin-role="exam-action"]').forEach(x=>x.classList.toggle('hidden',adminQuizWorkspaceMode!=='exams'));
}

function updateResultsWorkspacePresentation(){
    const title=document.getElementById('admin-results-title'), desc=document.getElementById('admin-results-desc');document.getElementById('admin-results-analytics')?.classList.toggle('hidden',adminResultWorkspaceMode!=='results');
    if(title) title.textContent=adminResultWorkspaceMode==='scoring'?'🎯 待人工評分':'📊 歷次考核成績';
    if(desc) desc.textContent=adminResultWorkspaceMode==='scoring'?'只顯示含問答題或尚待批改的考核，點「批改問答題」直接進入評分。':'顯示全部歷次成績，可匯出 Word / CSV。';
}

async function toggleAdminModal(show) {
    const modal = document.getElementById('admin-modal');
    if (show) {
        const key = await getAdminKey(); if (!key) return;
        populateAdminGroupSelects();
        const matSel=document.getElementById('admin-material-group'),quizSel=document.getElementById('admin-quiz-group');
        if(matSel)matSel.value=currentGroupKey;if(quizSel)quizSel.value=currentGroupKey;
        Object.keys(adminSectionLoaded).forEach(k=>adminSectionLoaded[k]=false);
        modal.classList.remove('hidden'); await switchAdminWorkspace('course-materials',false);
    } else modal.classList.add('hidden');
}

async function renderAdminAnnouncements(){
    const box=document.getElementById('admin-announcement-list'),status=document.getElementById('admin-announcement-status');if(!box)return;const key=await getAdminKey();if(!key)return;box.innerHTML='<div class="text-xs text-slate-400">讀取公告中…</div>';
    try{const r=await fetch('/api/announcements/admin',{headers:{'X-Admin-Key':key},cache:'no-store'}),rows=await r.json().catch(()=>[]);if(!r.ok)throw new Error(rows.error||'公告讀取失敗');box.innerHTML=rows.length?rows.map(a=>`<div class="rounded-xl border border-slate-200 bg-slate-50 p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div class="min-w-0"><div class="font-bold text-sm text-slate-900">${escapeHtml(a.title||'')}</div><div class="text-xs text-slate-500 mt-1 whitespace-pre-wrap">${escapeHtml(a.body||'')}</div><div class="text-[10px] mt-1 ${a.active?'text-emerald-700':'text-slate-400'}">${a.active?'● 已發布':'○ 已停用'} · ${escapeHtml((a.publishedAt||a.createdAt||'').slice(0,16).replace('T',' '))}</div></div><div class="flex gap-2 shrink-0"><button onclick="toggleAdminAnnouncement('${a.id}',${a.active?'false':'true'})" class="text-xs border border-slate-300 bg-white px-3 py-1.5 rounded-lg">${a.active?'停用':'發布'}</button><button onclick="deleteAdminAnnouncement('${a.id}')" class="text-xs text-rose-600 px-2 py-1.5">更多：刪除</button></div></div>`).join(''):'<div class="text-xs text-slate-400 py-3">尚無公告。</div>';if(status)status.textContent=`共 ${rows.length} 則公告`; }catch(e){box.innerHTML=`<div class="text-xs text-rose-600">❌ ${escapeHtml(e.message)}</div>`;}
}
async function createAdminAnnouncement(){const title=document.getElementById('admin-announcement-title')?.value.trim()||'',body=document.getElementById('admin-announcement-body')?.value.trim()||'',status=document.getElementById('admin-announcement-status');if(!title){status.textContent='❌ 請輸入公告標題';return;}const key=await getAdminKey();if(!key)return;status.textContent='⏳ 發布中…';const r=await fetch('/api/announcements',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({title,body,active:true})}),d=await r.json().catch(()=>({}));if(!r.ok){status.textContent='❌ '+(d.error||'發布失敗');return;}document.getElementById('admin-announcement-title').value='';document.getElementById('admin-announcement-body').value='';status.textContent='✅ 公告已發布到首頁';await renderAdminAnnouncements();}
async function toggleAdminAnnouncement(id,active){const key=await getAdminKey();if(!key)return;const r=await fetch(`/api/announcements/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})});if(!r.ok){const d=await r.json().catch(()=>({}));alert(d.error||'更新失敗');return;}await renderAdminAnnouncements();}
async function deleteAdminAnnouncement(id){if(!confirm('刪除此公告？這是永久刪除；若只是暫時不顯示，請使用「停用」。'))return;const key=await getAdminKey();if(!key)return;const r=await fetch(`/api/announcements/${encodeURIComponent(id)}`,{method:'DELETE',headers:{'X-Admin-Key':key}});if(!r.ok){const d=await r.json().catch(()=>({}));alert(d.error||'刪除失敗');return;}await renderAdminAnnouncements();}

async function renderAdminUserAccounts(){
    const body=document.getElementById('admin-user-accounts-body'),status=document.getElementById('admin-user-status');if(!body)return;body.innerHTML='<tr><td colspan="6" class="p-5 text-center text-slate-400">讀取帳號中…</td></tr>';
    const key=await getAdminKey();if(!key)return;
    try{const r=await fetch('/api/users',{headers:{'X-Admin-Key':key},cache:'no-store'}),rows=await r.json().catch(()=>[]);if(!r.ok)throw new Error(rows.error||'帳號讀取失敗');const roleLabel={learner:'學員',teacher:'教師',manager:'管理者'},areaLabel={internal:'院內',pgy:'PGY'};
        body.innerHTML=rows.length?rows.map(u=>`<tr class="${u.active?'':'opacity-55'}"><td class="p-3"><b>${escapeHtml(u.username)}</b><div class="text-slate-500 mt-1">${escapeHtml(u.name)}</div></td><td class="p-3 font-mono">${escapeHtml(u.empId)}</td><td class="p-3">${roleLabel[u.role]||escapeHtml(u.role)}</td><td class="p-3">${areaLabel[u.preferredArea]||''} · ${escapeHtml((GROUPS[u.preferredGroup]||GROUPS.grpBio).name)}</td><td class="p-3 text-slate-500">${escapeHtml((u.lastLoginAt||'尚未登入').slice(0,16).replace('T',' '))}</td><td class="p-3"><div class="flex flex-wrap gap-1.5"><button onclick="resetAdminUserPassword('${u.username}')" class="text-[11px] border border-slate-300 bg-white px-2.5 py-1.5 rounded-lg">重設密碼</button><button onclick="toggleAdminUserAccount('${u.username}',${u.active?'false':'true'})" class="text-[11px] ${u.active?'text-rose-600 border-rose-200':'text-emerald-700 border-emerald-200'} border bg-white px-2.5 py-1.5 rounded-lg">${u.active?'停用':'啟用'}</button></div></td></tr>`).join(''):'<tr><td colspan="6" class="p-5 text-center text-slate-400">尚未建立登入帳號。請使用上方表單建立第一個帳號。</td></tr>';if(status)status.textContent=`共 ${rows.length} 個帳號；登入預設自動記憶 30 天。`;
    }catch(e){body.innerHTML=`<tr><td colspan="6" class="p-5 text-center text-rose-600">❌ ${escapeHtml(e.message)}</td></tr>`;}
}
async function createAdminUserAccount(){
    const status=document.getElementById('admin-user-status'),key=await getAdminKey();if(!key)return;const payload={username:document.getElementById('admin-user-username')?.value||'',password:document.getElementById('admin-user-password')?.value||'',name:document.getElementById('admin-user-name')?.value||'',empId:document.getElementById('admin-user-empid')?.value||'',role:document.getElementById('admin-user-role')?.value||'learner',preferredArea:document.getElementById('admin-user-area')?.value||'internal',preferredGroup:document.getElementById('admin-user-group')?.value||'grpBio'};status.textContent='⏳ 建立帳號中…';
    const r=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)}),d=await r.json().catch(()=>({}));if(!r.ok){status.textContent='❌ '+(d.error||'建立失敗');return;}['admin-user-username','admin-user-password','admin-user-name','admin-user-empid'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});status.textContent=`✅ 已建立 ${d.user.name}（${d.user.username}）`;await renderAdminUserAccounts();
}
async function resetAdminUserPassword(username){const password=prompt(`請輸入「${username}」的新密碼（至少 8 碼）：`);if(password===null)return;const key=await getAdminKey();if(!key)return;const r=await fetch(`/api/users/${encodeURIComponent(username)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({password})}),d=await r.json().catch(()=>({}));alert(r.ok?'密碼已重設，該帳號需重新登入。':(d.error||'重設失敗'));if(r.ok)await renderAdminUserAccounts();}
async function toggleAdminUserAccount(username,active){const key=await getAdminKey();if(!key)return;const r=await fetch(`/api/users/${encodeURIComponent(username)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})}),d=await r.json().catch(()=>({}));if(!r.ok){alert(d.error||'更新失敗');return;}await renderAdminUserAccounts();}

async function renderAdminPeople(force=false){
    await renderAdminUserAccounts();
    const body=document.getElementById('admin-people-body'),sum=document.getElementById('admin-people-summary');if(!body||!sum)return;body.innerHTML='<tr><td colspan="5" class="p-5 text-center text-slate-400">讀取中…</td></tr>';
    try{const records=await fetchAdminRecords();if(!records)return;const map=new Map();for(const r of records){const k=(r.empId||'')+'|'+(r.name||'');if(!k.replace('|',''))continue;const old=map.get(k)||{name:r.name||'',empId:r.empId||'',role:r.role||'',count:0,last:r.timestamp||''};old.count++;if((r.timestamp||'')>=(old.last||'')){old.last=r.timestamp||'';old.role=r.role||old.role;}map.set(k,old);}const list=[...map.values()].sort((a,b)=>(b.last||'').localeCompare(a.last||''));const roles=new Set(list.map(x=>x.role).filter(Boolean));sum.innerHTML=`<div class="rounded-xl bg-sky-50 border border-sky-100 p-4"><span class="text-xs text-sky-700">近期人員</span><b class="block text-2xl text-sky-950 mt-1">${list.length}</b></div><div class="rounded-xl bg-slate-50 border border-slate-200 p-4"><span class="text-xs text-slate-500">身份類型</span><b class="block text-2xl text-slate-900 mt-1">${roles.size}</b></div><div class="rounded-xl bg-emerald-50 border border-emerald-100 p-4"><span class="text-xs text-emerald-700">考核紀錄</span><b class="block text-2xl text-emerald-950 mt-1">${records.length}</b></div>`;body.innerHTML=list.length?list.map(x=>`<tr><td class="p-3 font-bold">${escapeHtml(x.name)}</td><td class="p-3 font-mono">${escapeHtml(x.empId)}</td><td class="p-3">${escapeHtml(x.role||'—')}</td><td class="p-3">${x.count}</td><td class="p-3 text-slate-500">${escapeHtml(x.last||'')}</td></tr>`).join(''):'<tr><td colspan="5" class="p-5 text-center text-slate-400">尚無考核人員資料</td></tr>';}
    catch(e){body.innerHTML=`<tr><td colspan="5" class="p-5 text-center text-rose-500">❌ ${escapeHtml(e.message)}</td></tr>`;}
}
function systemStatusCard(icon,title,state,detail,tone='slate'){const classes={emerald:'border-emerald-200 bg-emerald-50 text-emerald-900',amber:'border-amber-200 bg-amber-50 text-amber-900',rose:'border-rose-200 bg-rose-50 text-rose-900',slate:'border-slate-200 bg-slate-50 text-slate-900'};return `<div class="rounded-xl border p-4 ${classes[tone]||classes.slate}"><div class="text-sm font-black">${icon} ${escapeHtml(title)}</div><div class="text-xs font-bold mt-2">${escapeHtml(state)}</div><div class="text-[11px] opacity-75 mt-1 break-all">${escapeHtml(detail||'')}</div></div>`;}
async function renderAdminSystemStatus(force=false){const cards=document.getElementById('admin-system-health'),storage=document.getElementById('admin-system-storage');if(!cards||!storage)return;cards.innerHTML='<div class="col-span-full text-xs text-slate-400">檢查服務中…</div>';storage.textContent='讀取儲存狀態中…';const key=await getAdminKey();if(!key)return;try{const [hr,sr,ar]=await Promise.all([fetch('/health'),fetch(`/api/storage-status${force?'?refresh=1':''}`,{headers:{'X-Admin-Key':key}}),fetch('/api/ai-questions/status',{headers:{'X-Admin-Key':key}})]);const h=await hr.json().catch(()=>({})),s=await sr.json().catch(()=>({})),a=await ar.json().catch(()=>({}));const dbOk=!!h.ok;cards.innerHTML=systemStatusCard('🖥️','Render / Web',dbOk?'正常':'異常',h.service||'',dbOk?'emerald':'rose')+systemStatusCard('🗄️','Supabase / Database',dbOk?'可連線':'待確認','健康檢查已通過即表示 Flask 與初始化流程正常',dbOk?'emerald':'amber')+systemStatusCard('🟣','MEGA',s.megaConfigured?(s.megaError?'已設定但檢查失敗':'已設定'):'未設定',s.megaSpace?`${s.megaSpace.usedGb??'?'} / ${s.megaSpace.totalGb??'?'} GB；網站上限 ${s.megaFreeLimitGb||18} GB`:(s.megaError||''),s.megaConfigured&&!s.megaError?'emerald':(s.megaConfigured?'amber':'rose'))+systemStatusCard('🤖','Groq AI',a.configured?'已設定':'未設定',`${a.provider||''} ${a.model||''}`,a.configured?'emerald':'amber');const g=s.gdriveConfigured?(s.gdriveConnected?'✅ Google Drive 備援已連線':((s.activeBackend||s.configuredMode)==='gdrive'?'⚠️ Google Drive 目前使用中，但連線尚未驗證':'ℹ️ Google Drive 備援已設定，尚未執行連線測試（不影響目前主要儲存）')):'○ Google Drive 備援未設定';storage.innerHTML=`<div class="font-black text-slate-900">教材儲存策略</div><div class="mt-2">主要：<b>${escapeHtml(s.activeBackend||s.configuredMode||'')}</b>　｜　備援：<b>${escapeHtml(s.fallbackBackend||'')}</b>　｜　免費模式：<b>${s.megaFreeOnly?'是':'否'}</b></div><div class="mt-2">${g}</div><div class="mt-2 text-xs text-slate-500">MEGA ${s.materials?.mega||0} 份、Google Drive ${s.materials?.gdrive||0} 份、R2 ${s.materials?.r2||0} 份、本機 ${s.materials?.local||0} 份</div>${s.error?`<div class="mt-2 text-rose-600">${escapeHtml(s.error)}</div>`:''}`;}catch(e){cards.innerHTML=systemStatusCard('⚠️','系統狀態','檢查失敗',e.message,'rose');storage.textContent='無法讀取儲存狀態';}}

function difficultyLabel(d){return ({basic:'基礎',standard:'一般',advanced:'進階'})[d||'standard']||'一般';}
function renderFilteredQuestionList(catId){const box=document.getElementById(`qlist-${catId}`);if(!box)return;const all=adminQuizQuestionCache[catId]||[],txt=(document.getElementById(`qfilter-text-${catId}`)?.value||'').trim().toLowerCase(),type=document.getElementById(`qfilter-type-${catId}`)?.value||'',diff=document.getElementById(`qfilter-difficulty-${catId}`)?.value||'',active=document.getElementById(`qfilter-active-${catId}`)?.value||'';const list=all.filter(q=>{if(type&&(q.questionType||'choice')!==type)return false;if(diff&&(q.difficulty||'standard')!==diff)return false;if(active==='active'&&q.active===false)return false;if(active==='inactive'&&q.active!==false)return false;if(txt&&!`${q.question||''} ${q.tag||''} ${q.explanation||''}`.toLowerCase().includes(txt))return false;return true;});box.innerHTML=list.length?list.map((q,i)=>adminQuestionRowHTML(q,i,catId)).join(''):`<p class="text-xs text-slate-400 py-4 text-center">${all.length?'沒有符合篩選條件的題目。':'目前尚無題目，可使用 AI、手動新增或公開連結匯入。'}</p>`;adminUpdateQuestionSelection(catId);}

async function previewCurrentExam(){const catId=document.getElementById('exam-settings-id')?.value;if(!catId)return;const panel=document.getElementById('exam-preview-panel'),list=document.getElementById('exam-preview-list'),meta=document.getElementById('exam-preview-meta');panel?.classList.remove('hidden');if(list)list.innerHTML='<p class="text-xs text-slate-400">建立預覽中…</p>';try{const key=await getAdminKey();const r=await fetch(`/api/quiz-questions/admin?category=${encodeURIComponent(catId)}`,{headers:{'X-Admin-Key':key}}),all=await r.json();if(!r.ok)throw new Error(all.error||'讀取題庫失敗');const active=all.filter(q=>q.active!==false),quotaMode=document.getElementById('exam-draw-quota')?.checked,limited=document.getElementById('exam-draw-limited')?.checked;let qs=[...active];if(quotaMode){const quotas=Object.fromEntries(['choice','multi','true_false','fill','essay','image','video'].map(k=>[k,Math.max(0,Number(document.getElementById(`exam-quota-${k}`)?.value||0))]));let chosen=[],ids=new Set();for(const t of Object.keys(quotas)){const pool=qs.filter(q=>(q.questionType||'choice')===t).sort(()=>Math.random()-.5);for(const q of pool.slice(0,quotas[t])){chosen.push(q);ids.add(q.id);}}const target=Object.values(quotas).reduce((a,b)=>a+b,0),remain=qs.filter(q=>!ids.has(q.id)).sort(()=>Math.random()-.5);chosen.push(...remain.slice(0,Math.max(0,target-chosen.length)));qs=chosen.sort(()=>Math.random()-.5);}else{qs.sort(()=>Math.random()-.5);if(limited){const n=Math.max(1,Number(document.getElementById('exam-settings-draw-count')?.value||1));qs=qs.slice(0,Math.min(n,qs.length));}}if(meta)meta.innerHTML=`考卷：<b>${escapeHtml(document.getElementById('exam-settings-title')?.value||'')}</b>　｜　本次預覽 <b>${qs.length}</b> 題　｜　及格 <b>${Number(document.getElementById('exam-settings-passing-score')?.value||80)}</b> 分`;if(list)list.innerHTML=qs.length?qs.map((q,i)=>`<div class="rounded-xl border border-slate-200 bg-white p-4"><div class="flex gap-2 flex-wrap mb-2"><span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">${questionTypeLabel(q.questionType)}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">${difficultyLabel(q.difficulty)}</span></div><div class="font-bold text-sm text-slate-900">${i+1}. ${escapeHtml(q.question||'')}</div>${(q.options||[]).length?`<div class="mt-2 grid sm:grid-cols-2 gap-2 text-xs">${q.options.map((o,j)=>`<div class="rounded-lg border border-slate-200 px-3 py-2">${String.fromCharCode(65+j)}. ${escapeHtml(o)}</div>`).join('')}</div>`:''}${q.questionType==='essay'?'<textarea disabled rows="3" class="mt-2 w-full border rounded-lg bg-slate-50 p-2 text-xs" placeholder="考生問答輸入區"></textarea>':''}</div>`).join(''):'<p class="text-xs text-amber-700">目前沒有可預覽的啟用題目。</p>';}catch(e){if(list)list.innerHTML=`<p class="text-xs text-rose-600">❌ ${escapeHtml(e.message)}</p>`;}}

function renderResultsAnalytics(records){const wrap=document.getElementById('admin-results-analytics'),cards=document.getElementById('admin-analytics-cards'),qbox=document.getElementById('admin-question-analytics');if(!wrap||!cards||!qbox)return;wrap.classList.toggle('hidden',adminResultWorkspaceMode!=='results');if(adminResultWorkspaceMode!=='results')return;const completed=(records||[]).filter(r=>r.reviewStatus!=='pending'&&Number.isFinite(Number(r.score))),pending=(records||[]).filter(r=>r.reviewStatus==='pending').length,avg=completed.length?completed.reduce((s,r)=>s+Number(r.score||0),0)/completed.length:0,passed=completed.filter(r=>(r.status||'')==='合格').length,rate=completed.length?Math.round(passed/completed.length*100):0;cards.innerHTML=`<div class="rounded-xl bg-slate-50 border p-4"><span class="text-xs text-slate-500">總考核次數</span><b class="block text-2xl mt-1">${records.length}</b></div><div class="rounded-xl bg-teal-50 border border-teal-100 p-4"><span class="text-xs text-teal-700">平均分</span><b class="block text-2xl mt-1 text-teal-950">${avg.toFixed(1)}</b></div><div class="rounded-xl bg-emerald-50 border border-emerald-100 p-4"><span class="text-xs text-emerald-700">通過率</span><b class="block text-2xl mt-1 text-emerald-950">${rate}%</b></div><div class="rounded-xl bg-amber-50 border border-amber-100 p-4"><span class="text-xs text-amber-700">待人工批改</span><b class="block text-2xl mt-1 text-amber-950">${pending}</b></div>`;const map=new Map();for(const r of records||[]){for(const a of r.answersDetail||[]){if(a.questionType==='essay'||a.isCorrect===null||a.isCorrect===undefined)continue;const k=a.questionText||`第${a.num||''}題`;const x=map.get(k)||{text:k,total:0,correct:0};x.total++;if(a.isCorrect===true)x.correct++;map.set(k,x);}}const list=[...map.values()].map(x=>({...x,rate:x.total?Math.round(x.correct/x.total*100):0})).sort((a,b)=>a.rate-b.rate||b.total-a.total).slice(0,12);qbox.innerHTML=list.length?list.map(x=>`<div class="rounded-xl border ${x.rate<60?'border-rose-200 bg-rose-50/40':'border-slate-200 bg-white'} p-3 flex items-center justify-between gap-3"><div class="min-w-0"><div class="text-xs font-bold text-slate-800 line-clamp-2">${escapeHtml(x.text)}</div><div class="text-[11px] text-slate-500 mt-1">作答 ${x.total} 次・答對 ${x.correct} 次</div></div><div class="shrink-0 text-sm font-black ${x.rate<60?'text-rose-700':'text-teal-700'}">${x.rate}%</div></div>`).join(''):'<p class="text-xs text-slate-400">目前沒有足夠的客觀題作答紀錄可分析。</p>';}

async function fetchAdminRecords() {
    const key = await getAdminKey();
    if (!key) return null;
    const res = await fetch('/api/records', { headers: { 'X-Admin-Key': key } });
    if (res.status === 401) {
        sessionStorage.removeItem('admin_key');
        adminKey = '';
        alert('管理者金鑰錯誤或尚未設定，請重新輸入。');
        return null;
    }
    const data = await res.json().catch(() => []);
    if (!res.ok) throw new Error(data.error || '無法取得成績');
    adminRecords = Array.isArray(data) ? data : [];
    return adminRecords;
}

async function renderAdminTable() {
    updateResultsWorkspacePresentation();
    const tbody = document.getElementById('admin-table-body');
    tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">讀取伺服器成績中…</td></tr>`;
    try {
        const records = await fetchAdminRecords();
        if (!records) return;
        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">目前尚無任何考核紀錄</td></tr>`;
            return;
        }
        renderResultsAnalytics(records);
        const visibleRecords = adminResultWorkspaceMode==='scoring' ? records.filter(r => r.reviewStatus==='pending' || (r.answersDetail||[]).some(a=>a.questionType==='essay')) : records;
        if(visibleRecords.length===0){tbody.innerHTML=`<tr><td colspan="8" class="p-6 text-center text-slate-400">${adminResultWorkspaceMode==='scoring'?'目前沒有待人工評分的考核。':'目前尚無任何考核紀錄'}</td></tr>`;return;}
        tbody.innerHTML = visibleRecords.map((r) => { const index=records.indexOf(r); return `
            <tr class="hover:bg-slate-50 transition-colors">
                <td class="p-3 font-mono text-slate-500">${r.timestamp || ''}</td>
                <td class="p-3"><span class="px-2 py-0.5 rounded-full text-xs font-medium bg-teal-50 text-teal-700">${escapeHtml(r.groupLabel || '1 生化組')}</span></td>
                <td class="p-3 font-bold text-slate-800">${r.name || ''}</td>
                <td class="p-3 font-mono">${r.empId || ''}</td>
                <td class="p-3">${r.quizTitle || ''}</td>
                <td class="p-3 text-center font-bold ${r.reviewStatus === 'pending' ? 'text-amber-600' : (Number(r.score) >= Number(r.passingScore||80) ? 'text-green-600' : 'text-red-600')}">${r.reviewStatus === 'pending' ? '待批改' : (Number(r.score) || 0)}</td>
                <td class="p-3 text-center"><span class="px-2 py-0.5 rounded-full text-xs font-bold ${r.reviewStatus === 'pending' ? 'bg-amber-100 text-amber-800' : (r.status === '合格' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800')}">${r.status || ''}</span></td>
                <td class="p-3 text-center space-y-1">
                    ${(r.answersDetail||[]).some(a=>a.questionType==='essay') ? `<button onclick="openEssayReview(${index})" class="bg-rose-600 hover:bg-rose-500 text-white text-xs px-2.5 py-1 rounded shadow-sm">✍️ ${r.reviewStatus==='pending'?'批改問答題':'重新批改'}</button>` : ''}
                    <button onclick="exportRecordToWord(${index})" class="bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-2.5 py-1 rounded transition-colors shadow-sm">📄 匯出 Word</button>
                </td>
            </tr>
        `; }).join('');
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-rose-500">❌ ${error.message}</td></tr>`;
    }
}

// --- 附件1 匯出功能 (支援後台直接匯出或目前頁籤即時匯出) ---
// 生化組：沿用原本「匯出時於瀏覽器選一次附件1.docx，之後快取沿用」的方式。
// 六組皆優先使用管理者已上傳到伺服器的該組別空白範本，自動抓取並直接填入匯出，
// 不需要每次匯出都手動選檔。
let cachedTemplateBuffer = null;
let adminRecords = [];
let adminKey = sessionStorage.getItem('admin_key') || '';
let pendingExportRecordIndex = null;
let isExportingCurrentTab = false;

function buildRoleCheckboxText(role, groupKey = currentGroupKey) {
    const memberRole = getGroupMemberRole(groupKey);
    const duty = role === '值班醫檢師' ? '☑' : '□';
    const member = role === memberRole ? '☑' : '□';
    return `${duty}值班醫檢師 ${member}${memberRole}`;
}

function buildEvaluatorTitleCheckboxText(title) {
    const leader = title === '組長' ? '☑' : '□';
    const senior = title === '資深醫檢師' ? '☑' : '□';
    return `${leader}組長 ${senior}資深醫檢師`;
}

// 組出目前頁籤（作答中）的匯出資料與檔名
function buildCurrentTabDocPayload() {
    const nameInput = document.getElementById('examinee-name').value.trim();
    const idInput = document.getElementById('examinee-id').value.trim();
    const roleInput = document.getElementById('examinee-role').value;
    const evaluatorNameInput = document.getElementById('evaluator-name').value.trim();
    const evaluatorTitleInput = document.getElementById('evaluator-title').value;
    const quizList = allQuizData[currentCatKey].questions;
    const userAnswers = userAnswersMap[currentCatKey];
    const optionLetters = ['A', 'B', 'C', 'D', 'E', 'F'];
    const answersDetail = quizList.map((q, idx) => {
        const isEssay=(q.questionType||'choice')==='essay';
        const ans=userAnswers[idx];
        return {num:idx+1, questionText:q.question, questionType:isEssay?'essay':'choice', userAnswer:isEssay?(String(ans||'未作答')):(ans!==null && ans!=='' ? optionLetters[ans] : '未作答')};
    });
    const choiceRows=quizList.map((q,idx)=>({q,idx})).filter(x=>(x.q.questionType||'choice')!=='essay');
    const correctCount=choiceRows.filter(x=>userAnswers[x.idx]===x.q.correct).length;
    const wrongCount=choiceRows.length-correctCount;
    const essayCount=quizList.length-choiceRows.length;
    const evaluationScore=quizList.length>0 ? Math.round((correctCount/quizList.length)*100) : 0;
    const passingScore=Math.max(1,Math.min(100,Number(allQuizData[currentCatKey]?.passingScore||80)));
    const evaluationStatus=essayCount>0 ? '待人工批改' : (evaluationScore>=passingScore?'合格':'不合格');
    return {payload:{name:nameInput,empId:idInput,role:buildRoleCheckboxText(roleInput,currentGroupKey),evaluator:evaluatorNameInput,evaluatorTitle:buildEvaluatorTitleCheckboxText(evaluatorTitleInput),score:evaluationScore,evaluationScore,passingScore,correctCount,wrongCount,totalQuestions:quizList.length,status:evaluationStatus,result:evaluationStatus,questions:answersDetail},filenamePart:`${GROUPS[currentGroupKey].label}年度人員能力考核表_${allQuizData[currentCatKey].title}_${nameInput}`};
}

// 組出後台某一筆已存檔成績的匯出資料與檔名
function buildRecordDocPayload(rec) {
    const recordScore = Number.isFinite(Number(rec.score)) ? Number(rec.score) : 0;
    const recordAnswers = Array.isArray(rec.answersDetail) ? rec.answersDetail : [];
    const recordCorrect = recordAnswers.filter(a => a.questionType !== 'essay' && a.isCorrect === true).length;
    const recordWrong = recordAnswers.filter(a => a.questionType !== 'essay' && a.isCorrect === false).length;
    const groupLabel = (GROUPS[rec.groupKey] || GROUPS.grpBio).label;
    const passingScore=Math.max(1,Math.min(100,Number(rec.passingScore||80)));
    const recordStatus=rec.status || (recordScore>=passingScore?'合格':'不合格');
    return {payload:{name:rec.name,empId:rec.empId,role:buildRoleCheckboxText(rec.role,rec.groupKey||'grpBio'),evaluator:rec.evaluatorName||'',evaluatorTitle:buildEvaluatorTitleCheckboxText(rec.evaluatorTitle),score:recordScore,evaluationScore:recordScore,passingScore,correctCount:recordCorrect,wrongCount:recordWrong,totalQuestions:recordAnswers.length,status:recordStatus,result:recordStatus,questions:recordAnswers},filenamePart:`${groupLabel}年度人員能力考核表_${rec.name}_${rec.empId}`};
}

// 用給定的範本二進位內容 (ArrayBuffer) 填入資料並下載，成功回傳 true
function renderDocxFromBuffer(templateBuffer, payload, filenamePart) {
    try {
        const zip = new PizZip(templateBuffer);
        const doc = new window.docxtemplater(zip, { paragraphLoop: true, linebreaks: true });
        doc.render(payload);
        const blob = doc.getZip().generate({
            type: "blob",
            mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        });
        saveAs(blob, `附件1.${filenamePart}.docx`);
        return true;
    } catch (error) {
        console.error(error);
        alert(`匯出失敗：
${error.message}

請確認範本檔案格式正確（.docx，且佔位字未被 Word 自動校正拆散）。`);
        return false;
    }
}

// 依組別代碼向伺服器抓取該組已上傳的空白範本並直接匯出
async function exportWithServerTemplate(groupKey, payload, filenamePart, silentMissing=false) {
    try {
        const res = await fetch(`/api/doc-templates/${groupKey}/download`);
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            if (!silentMissing) alert(data.error || `「${GROUPS[groupKey].label}」尚未上傳 Word 匯出範本，請至管理後台「Word 範本」上傳 .docx。`);
            return false;
        }
        const buffer = await res.arrayBuffer();
        return renderDocxFromBuffer(buffer, payload, filenamePart);
    } catch (err) { console.error(err); if(!silentMissing) alert(`讀取範本失敗：${err.message}`); return false; }
}

async function exportCurrentTabToWord() {
    const nameInput = document.getElementById('examinee-name').value.trim();
    const idInput = document.getElementById('examinee-id').value.trim();
    const roleInput = document.getElementById('examinee-role').value;
    const evaluatorNameInput = document.getElementById('evaluator-name').value.trim();
    const evaluatorTitleInput = document.getElementById('evaluator-title').value;
    if (!nameInput || !idInput || !roleInput || !evaluatorNameInput || !evaluatorTitleInput) {
        alert('請先填寫「受測人員姓名」「員工工號」「考試人員類別」「考核人員姓名」與「考核人員職稱」再執行匯出！'); return;
    }
    rememberEvaluatorFields();
    const { payload, filenamePart } = buildCurrentTabDocPayload();
    const ok = await exportWithServerTemplate(currentGroupKey, payload, filenamePart, currentGroupKey === 'grpBio');
    if (!ok && currentGroupKey === 'grpBio') {
        isExportingCurrentTab = true;
        if (cachedTemplateBuffer) generateCurrentTabWord();
        else { alert('後台尚未上傳生化組 Word 範本。可暫時選擇本機「附件1.docx」匯出，或請管理者至後台上傳範本。'); document.getElementById('docx-template-input').click(); }
    }
}

function generateCurrentTabWord() {
    const { payload, filenamePart } = buildCurrentTabDocPayload();
    if (!renderDocxFromBuffer(cachedTemplateBuffer, payload, filenamePart)) {
        cachedTemplateBuffer = null;
    }
}

async function exportRecordToWord(recordIndex) {
    const rec = adminRecords[recordIndex];
    if (!rec) { alert('找不到這筆伺服器成績，請重新整理後台。'); return; }
    const groupKey = rec.groupKey || 'grpBio';
    const { payload, filenamePart } = buildRecordDocPayload(rec);
    const ok = await exportWithServerTemplate(groupKey, payload, filenamePart, groupKey === 'grpBio');
    if (!ok && groupKey === 'grpBio') {
        isExportingCurrentTab = false; pendingExportRecordIndex = recordIndex;
        if (cachedTemplateBuffer) generateWordFromTemplate(recordIndex);
        else { alert('後台尚未上傳生化組 Word 範本。可暫時選擇本機「附件1.docx」匯出。'); document.getElementById('docx-template-input').click(); }
    }
}

function generateWordFromTemplate(recordIndex) {
    const rec = adminRecords[recordIndex];
    if (!rec) { alert('找不到這筆伺服器成績，請重新整理後台。'); return; }
    const { payload, filenamePart } = buildRecordDocPayload(rec);
    if (!renderDocxFromBuffer(cachedTemplateBuffer, payload, filenamePart)) {
        cachedTemplateBuffer = null;
    }
}

document.getElementById('docx-template-input').addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (evt) {
        cachedTemplateBuffer = evt.target.result;
        if (isExportingCurrentTab) {
            generateCurrentTabWord();
        } else if (pendingExportRecordIndex !== null) {
            const idx = pendingExportRecordIndex;
            pendingExportRecordIndex = null;
            generateWordFromTemplate(idx);
        }
    };
    reader.onerror = function () {
        alert('讀取範本檔案失敗。');
    };
    reader.readAsArrayBuffer(file);
    e.target.value = '';
});

async function exportToCSV() {
    try {
        const records = await fetchAdminRecords();
        if (!records || records.length === 0) {
            alert('目前無可供匯出的紀錄！');
            return;
        }
        let csvContent = "\ufeff考核時間,組別,姓名,工號,考試人員類別,考核人員,考核人員職稱,考卷主題,得分,考核結果\n";
        records.forEach(r => {
            csvContent += `"${r.timestamp || ''}","${r.groupLabel || '1 生化組'}","${r.name || ''}","${r.empId || ''}","${r.role || ''}","${r.evaluatorName || ''}","${r.evaluatorTitle || ''}","${r.quizTitle || ''}",${Number(r.score) || 0},"${r.status || ''}"\n`;
        });
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `生化組教育訓練考核成績表_${new Date().toISOString().slice(0,10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        alert(`匯出失敗：${error.message}`);
    }
}

async function clearAllRecords() {
    if (!confirm('確定要清空伺服器後台所有歷史考核成績紀錄嗎？此操作無法復原。')) return;
    const key = await getAdminKey();
    if (!key) return;
    try {
        const res = await fetch('/api/records', { method: 'DELETE', headers: { 'X-Admin-Key': key } });
        const data = await res.json().catch(() => ({}));
        if (res.status === 401) { sessionStorage.removeItem('admin_key'); adminKey = ''; }
        if (!res.ok) throw new Error(data.error || '清空失敗');
        adminRecords = [];
        await renderAdminTable();
    } catch (error) {
        alert(`清空失敗：${error.message}`);
    }
}

function renderCategoryChart(categoryStats) {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();
    }

    const labels = Object.keys(categoryStats);
    const userScores = labels.map(cat => categoryStats[cat].correct);
    const maxScores = labels.map(cat => categoryStats[cat].total);

    chartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '答對題數',
                    data: userScores,
                    backgroundColor: 'rgba(13, 148, 136, 0.85)',
                    borderColor: '#0f766e',
                    borderWidth: 1
                },
                {
                    label: '該項題數',
                    data: maxScores,
                    backgroundColor: 'rgba(226, 232, 240, 0.7)',
                    borderColor: '#cbd5e1',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1 }
                }
            },
            plugins: {
                legend: { position: 'top' }
            }
        }
    });
}

function resetCurrentQuiz() {
    if (confirm('確定要重置本分頁試卷並清空已選答案與解鎖填答限制嗎？')) {
        isSubmittedMap[currentCatKey] = false;
        const qCount = allQuizData[currentCatKey].questions.length;
        userAnswersMap[currentCatKey] = new Array(qCount).fill(null);
        flaggedQuestionsMap[currentCatKey] = new Array(qCount).fill(false);
        clearExamDraft(currentCatKey);
        saveExamDraft(currentCatKey);
        document.getElementById('result-dashboard').classList.add('hidden');
        renderQuestions();
        updateProgressStats();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function toggleSopModal(show) {
    const modal = document.getElementById('sop-modal');
    if (show) {
        modal.classList.remove('hidden');
    } else {
        modal.classList.add('hidden');
    }
}
