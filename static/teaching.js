/* Teaching workflow additions. Page bookmarks are device-local, never completion evidence. */
let teachingIdentity = null;
let teachingEditor = null;
let teachingEditorBusy = false;
let teachingReaderBusy = false;
let teachingIdentityRequest = 0;
let teachingMediaId = '';

function teachingOrderedMaterials(course, materials) {
    const order = new Map((course?.materialOrder || []).map((id, i) => [id, i]));
    return [...materials].sort((a, b) => (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity));
}
function teachingBookmarkKey(id) {
    return 'teaching-page-v1:' + JSON.stringify([currentTrainingArea, currentGroupKey, teachingIdentity?.empId || 'guest', teachingIdentity?.name || '', id]);
}
function teachingReadPage(id, total) {
    try {
        const page = Number(localStorage.getItem(teachingBookmarkKey(id)));
        return Number.isInteger(page) && page >= 0 && page < total ? page : 0;
    } catch (_) { return 0; }
}
function teachingSavePage() {
    const s = slideViewerState;
    const total = s.mode === 'pdf' ? Number(s.pageCount || 0) : Number(s.images?.length || 0);
    if (!s.materialId || total <= 0) return;
    let saved = true;
    try { localStorage.setItem(teachingBookmarkKey(s.materialId), String(s.index)); } catch (_) { saved = false; }
    const material = cachedSlidesList.find(m => m.id === s.materialId);
    const course = cachedCourses.find(c => c.id === material?.courseId);
    const context = document.getElementById('reader-learning-context');
    if (context) context.textContent = [course?.title, material?.desc, saved ? '已記住本頁（此瀏覽器）；閱讀完成請自行標記。' : '此瀏覽器無法保存頁碼；完成紀錄仍可送出。'].filter(Boolean).join(' ｜ ');
    const complete = document.getElementById('reader-complete');
    if (complete) {
        complete.hidden = !!material?.isBuiltin;
        complete.disabled = teachingReaderBusy || !!myCompletedMaterials[s.materialId];
        complete.textContent = myCompletedMaterials[s.materialId] ? '✓ 已完成' : '標記完成';
    }
    const next = document.getElementById('reader-next');
    if (next) next.disabled = teachingReaderBusy || !teachingFindNextMaterial();
}
function teachingFindNextMaterial(materialId = slideViewerState.materialId) {
    const material = cachedSlidesList.find(m => m.id === materialId);
    if (!material?.courseId) return null;
    const course = cachedCourses.find(c => c.id === material.courseId);
    const materials = teachingOrderedMaterials(course, cachedSlidesList.filter(m => m.courseId === material.courseId));
    return materials[materials.findIndex(m => m.id === material.id) + 1] || null;
}
function teachingNextMaterial() {
    const next = teachingFindNextMaterial();
    if (next) { closeSlideViewer(); openMaterial(next.id); }
}
async function teachingFinishReading() {
    if (teachingReaderBusy) return;
    teachingReaderBusy = true; teachingSavePage();
    try { await markMaterialComplete(slideViewerState.materialId); }
    finally { teachingReaderBusy = false; teachingSavePage(); }
}
function teachingWelcome() {
    const host = document.getElementById('learning-start');
    if (!host || host.dataset.ready) return;
    host.dataset.ready = '1';
    host.innerHTML = `<section class="teaching-welcome v573-teaching-welcome"><div><h3>依課程順序，開始今天的學習</h3><p>學習身分已與首頁連動。閱讀教材、完成標記與考核紀錄都使用首頁的工號識別，不需要在內頁再次輸入。</p></div><div class="v573-linked-identity compact"><div><b id="learning-linked-name">尚未設定個人資料</b><span id="learning-linked-id">請先回首頁設定姓名與工號</span></div><a href="/">回首頁設定</a></div><p id="learning-identity-status" class="teaching-status" role="status">正在檢查首頁個人資料…</p></section>`;
    teachingLoadHomeIdentity();
}
async function teachingLoadHomeIdentity() {
    const name = (()=>{try{return localStorage.getItem('smh_learner_name')||''}catch(_){return ''}})();
    const empId = (()=>{try{return localStorage.getItem('smh_learner_empid')||''}catch(_){return ''}})();
    const nameEl=document.getElementById('learning-linked-name'), idEl=document.getElementById('learning-linked-id'), status=document.getElementById('learning-identity-status');
    if(nameEl) nameEl.textContent=name||'尚未設定姓名';
    if(idEl) idEl.textContent=empId?`工號 ${empId}`:'請先回首頁設定姓名與工號';
    teachingSetIdentityFields(name,empId);
    if(!name||!empId){ teachingIdentity=null; myCompletedMaterials={}; if(status){status.classList.add('error');status.textContent='尚未完成首頁個人資料設定；教材仍可閱讀，但完成紀錄與考核無法寫入。';} renderCourseOverview(); return; }
    const requestId=++teachingIdentityRequest, area=currentTrainingArea, group=currentGroupKey;
    if(status){status.classList.remove('error');status.textContent='正在載入你的教材完成紀錄…';}
    try{
        const res=await fetch('/api/my-progress?'+new URLSearchParams({name,empId,area,group}));
        const data=await res.json(); if(!res.ok) throw Error(data.error||'無法載入學習紀錄');
        if(requestId!==teachingIdentityRequest||area!==currentTrainingArea||group!==currentGroupKey)return;
        teachingIdentity={name,empId}; myCompletedMaterials=data.materialsCompleted||{};
        if(status)status.textContent=`${name}，已由首頁載入你的完成紀錄。`;
        renderCourseOverview();
    }catch(err){ teachingIdentity=null; if(status){status.classList.add('error');status.textContent=err.message+'；請回首頁確認個人資料。';} }
}

function teachingSetIdentityFields(name, empId) {
    ['examinee-name', 'progress-name', 'learning-name'].forEach(id => { const el = document.getElementById(id); if (el) el.value = name; });
    ['examinee-id', 'progress-empid', 'learning-empid'].forEach(id => { const el = document.getElementById(id); if (el) el.value = empId; });
}
function teachingClearIdentity() {
    teachingIdentityRequest++;
    teachingIdentity = null; myCompletedMaterials = {};
    teachingSetIdentityFields('', '');
    document.getElementById('progress-summary')?.classList.add('hidden');
    const status = document.getElementById('learning-identity-status');
    if(status){status.classList.add('error');status.textContent='個人資料統一由首頁管理；請回首頁更新或清除。';}
    renderCourseOverview();
}

async function teachingLoadIdentity() { return teachingLoadHomeIdentity(); }

function teachingMaterialRow(m, index) {
    const done = !!myCompletedMaterials[m.id];
    const meta = courseMaterialMeta(m);
    const page = teachingReadPage(m.id, m.pageCount || 0);
    return `<div class="teaching-step"><span class="teaching-step-number">${done ? '✓' : index + 1}</span><div class="teaching-step-body"><h5>${escapeHtml(m.title || m.filename || '教材')}</h5><div class="teaching-meta"><span>${escapeHtml(meta.label)}</span>${m.pageCount ? `<span>${Number(m.pageCount)} 頁</span>` : ''}<span>${done ? '已完成閱讀' : page ? `上次讀到第 ${page + 1} 頁` : '尚未標記完成'}</span></div>${m.desc ? `<p>${escapeHtml(m.desc)}</p>` : ''}</div><div class="teaching-actions"><button class="teaching-primary" data-material-open="${escapeHtml(m.id)}">${page ? '繼續閱讀' : meta.key === 'media' ? '播放教材' : '閱讀教材'}</button>${m.isBuiltin ? '' : `<button class="teaching-secondary" data-material-complete="${escapeHtml(m.id)}" ${done ? 'disabled' : ''}>${done ? '✓ 已完成' : '標記完成'}</button>`}</div></div>`;
}
function renderCourseOverview() {
    const box = document.getElementById('course-overview'), grid = document.getElementById('course-overview-grid');
    if (!box || !grid) return;
    teachingWelcome(); box.classList.remove('hidden');
    const query = (document.getElementById('learning-search')?.value || '').trim().toLowerCase();
    const filter = document.getElementById('learning-filter')?.value || 'all';
    const courses = cachedCourses.filter(c => c.group === currentGroupKey && c.area === currentTrainingArea);
    const materials = cachedSlidesList.filter(m => (m.group || 'grpBio') === currentGroupKey && (m.area || currentTrainingArea) === currentTrainingArea);
    const quizzes = cachedQuizCategories.filter(q => (q.group || currentGroupKey) === currentGroupKey && (q.area || currentTrainingArea) === currentTrainingArea);
    const openIds = new Set([...grid.querySelectorAll('details[open]')].map(x => x.dataset.course));
    const hadCards = !!grid.querySelector('details');
    const unassigned = materials.filter(m => !courses.some(c => c.id === m.courseId));
    const unassignedExams = quizzes.filter(q => !courses.some(c => c.id === q.courseId));
    const all = [...courses];
    if (unassigned.length || unassignedExams.length) all.push({id:'__general__', title:'補充學習資源', desc:'依需要選讀的教材與評量。'});
    let shown = 0;
    grid.innerHTML = all.map((course, index) => {
        const general = course.id === '__general__';
        const mats = teachingOrderedMaterials(course, general ? unassigned : materials.filter(m => m.courseId === course.id));
        const exams = general ? unassignedExams : quizzes.filter(q => q.courseId === course.id);
        const done = mats.filter(m => myCompletedMaterials[m.id]).length;
        const complete = mats.length > 0 && done === mats.length;
        const haystack = [course.title,course.desc,course.learningObjectives,...mats.map(m => (m.title || '') + ' ' + (m.desc || ''))].join(' ').toLowerCase();
        if (query && !haystack.includes(query) || filter === 'todo' && (!mats.length || complete) || filter === 'done' && !complete) return '';
        shown++;
        const next = mats.find(m => !myCompletedMaterials[m.id]);
        const objectives = (course.learningObjectives || '').split('\n').map(s => s.trim()).filter(Boolean);
        const pct = mats.length ? Math.round(done / mats.length * 100) : 0;
        return `<details class="course-learning-card" data-course="${escapeHtml(course.id)}" ${openIds.has(course.id) || (!hadCards && shown === 1) ? 'open' : ''}><summary class="course-learning-summary"><div class="min-w-0 flex-1"><div class="teaching-course-header"><span class="teaching-course-number">${general ? '+' : String(index + 1).padStart(2,'0')}</span><h3 class="text-lg font-black">${escapeHtml(course.title)}</h3></div><div class="teaching-meta"><span>教材完成 ${done}／${mats.length}</span>${course.estimatedMinutes ? `<span>建議 ${course.estimatedMinutes} 分鐘</span>` : ''}${course.startDate || course.endDate ? `<span>建議學習期間：${escapeHtml(course.startDate || '不限')} ～ ${escapeHtml(course.endDate || '不限')}</span>` : ''}<span>課後評量 ${exams.length} 份</span></div>${mats.length ? `<div class="course-progress-mini mt-3" role="progressbar" aria-label="教材完成比例" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><span style="width:${pct}%"></span></div>` : ''}</div><span class="course-learning-chevron">⌄</span></summary><div class="teaching-plan"><div>${course.desc ? `<p>${escapeHtml(course.desc)}</p>` : ''}${objectives.length ? `<h4 class="mt-3">學完這堂課，你將能夠</h4><ul>${objectives.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>` : '<p class="teaching-help">依下方順序閱讀教材，再進行課後評量。</p>'}</div><div>${next ? `<button class="teaching-primary" data-material-open="${escapeHtml(next.id)}">${done ? '繼續下一份教材' : '開始學習'} →</button>` : `<p class="teaching-help">${complete ? '教材已完成，可複習或進行課後評量。' : '教師正在準備教材。'}</p>`}</div></div><div class="course-material-group"><h4 class="teaching-section-title">${general ? '選讀教材' : '學習路徑 · 請依序閱讀'}</h4>${mats.map(teachingMaterialRow).join('') || '<p class="teaching-help">尚無教材。</p>'}${exams.length ? `<div class="mt-5"><h4 class="teaching-section-title">課後評量</h4><p class="teaching-help">建議先完成教材。閱讀完成與考核通過分別計算。</p>${exams.map(buildCourseExamRow).join('')}</div>` : ''}</div></details>`;
    }).join('') || '<div class="course-empty-row">沒有符合條件的課程。請更換關鍵字或閱讀狀態；尚無課程時請聯絡教師。</div>';
    document.getElementById('learning-result-count').textContent = `顯示 ${shown} 個課程／資源區`;
    document.getElementById('course-overview-course-count').textContent = `課程 ${courses.length}`;
    document.getElementById('course-overview-material-count').textContent = `教材 ${materials.length}`;
    document.getElementById('course-overview-exam-count').textContent = `考卷 ${quizzes.length}`;
}

async function markMaterialComplete(materialId) {
    if (!teachingIdentity) {
        closeSlideViewer(); closeMediaViewer();
        teachingWelcome();
        const status = document.getElementById('learning-identity-status');
        status.textContent = '請先回首頁設定姓名與工號，再標記教材完成。';
        return false;
    }
    const identity = teachingIdentity;
    try {
        const res = await fetch('/api/material-progress', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...identity,materialId})});
        const data = await res.json();
        if (!res.ok) throw Error(data.error || '無法儲存完成紀錄');
        if (teachingIdentity !== identity) return false;
        myCompletedMaterials[materialId] = data.completedAt || true;
        if (currentMaterialView === 'materials') renderCourseOverview(); else await renderSlidesGrid();
        return true;
    } catch (err) { alert('完成紀錄尚未儲存：' + err.message + '。請重試。'); return false; }
}

function teachingEnsureDialog() {
    if (document.getElementById('teaching-dialog')) return;
    const dialog = document.createElement('dialog'); dialog.id = 'teaching-dialog'; dialog.className = 'teaching-dialog';
    dialog.setAttribute('aria-labelledby','teaching-dialog-title');
    dialog.innerHTML = `<header class="teaching-dialog-head"><div><h3 id="teaching-dialog-title">課程編排</h3><p class="teaching-help">安排學習目標、日期與教材閱讀順序。</p></div><button type="button" class="teaching-secondary" onclick="teachingCloseEditor()">關閉</button></header><form class="teaching-form" onsubmit="event.preventDefault();teachingSaveCourse()"><fieldset id="teaching-fields"><div class="teaching-form-grid"><label class="wide">課程名稱<input id="plan-title" maxlength="255" required></label><label class="wide">課程說明<textarea id="plan-desc" rows="2" maxlength="2000"></textarea></label><label class="wide">學習目標（每行一項）<textarea id="plan-objectives" rows="4" maxlength="4000" placeholder="例如：能說明本課程的操作流程與注意事項"></textarea></label><label>建議學習時間（分鐘；0 表示未設定）<input id="plan-minutes" type="number" min="0" max="10000" step="1" required></label><label>課程顯示順序（數字小的在前）<input id="plan-order" type="number" min="0" max="100000" step="1" required></label><label>建議開始日期<input id="plan-start" type="date"></label><label>建議完成日期<input id="plan-end" type="date"></label><label class="wide"><input id="plan-active" type="checkbox">啟用課程（顯示於學員課程列表）</label><p class="teaching-help wide">日期作為教學安排提示，不限制閱讀。停用課程不會連帶停用教材或考卷；如需隱藏資源，請另至教材與考卷管理停用。</p></div><h4 class="teaching-section-title mt-5">教材閱讀順序</h4><p class="teaching-help">使用上移／下移安排順序，儲存後學員畫面同步更新。新增或變更教材歸屬請至教材管理。</p><div id="plan-materials"></div></fieldset><footer class="teaching-form-footer"><p id="plan-status" class="teaching-status" role="status"></p><div class="teaching-actions"><button id="plan-save" class="teaching-primary" type="submit">儲存課程安排</button><button type="button" class="teaching-secondary" onclick="teachingCloseEditor()">取消</button></div></footer></form>`;
    dialog.addEventListener('cancel', e => { e.preventDefault(); teachingCloseEditor(); });
    document.body.append(dialog);
}
function teachingCloseEditor() {
    if (teachingEditorBusy) return;
    if (teachingEditor?.dirty && !confirm('尚有未儲存的課程修改，確定關閉？')) return;
    document.getElementById('teaching-dialog').close(); teachingEditor = null;
}
async function teachingEditCourse(id) {
    teachingEnsureDialog();
    const key = await getAdminKey(); if (!key) return;
    const dialog = document.getElementById('teaching-dialog');
    if (dialog.open) return;
    teachingEditorBusy = true; teachingEditor = null;
    document.getElementById('teaching-fields').disabled = true;
    document.getElementById('plan-save').disabled = true;
    const status = document.getElementById('plan-status'); status.classList.remove('error'); status.textContent = '載入課程安排中…';
    dialog.showModal();
    try {
        const res = await fetch(`/api/courses/${encodeURIComponent(id)}/plan`,{headers:{'X-Admin-Key':key}});
        const data = await res.json(); if (!res.ok) throw Error(data.error || '讀取失敗');
        const c = data.course;
        teachingEditor = {course:c, materials:teachingOrderedMaterials(c,data.materials), dirty:false};
        for (const [field,value] of Object.entries({title:c.title,desc:c.desc,objectives:c.learningObjectives,minutes:c.estimatedMinutes,order:c.sortOrder,start:c.startDate,end:c.endDate})) document.getElementById('plan-'+field).value = value ?? '';
        document.getElementById('plan-active').checked = c.active;
        teachingRenderOrder(); status.textContent = '修改後請按「儲存課程安排」。';
        document.getElementById('teaching-fields').disabled = false;
        document.getElementById('plan-save').disabled = false;
        document.getElementById('plan-title').focus();
    } catch (err) { status.classList.add('error'); status.textContent = err.message + '，請關閉後重試。'; }
    finally { teachingEditorBusy = false; }
}
function teachingRenderOrder(focusIndex, direction) {
    document.getElementById('plan-materials').innerHTML = teachingEditor.materials.map((m,i,arr) => `<div class="teaching-order"><span><b>${i+1}.</b> ${escapeHtml(m.title || m.filename)} ${m.active ? '' : '（已停用，學員不顯示）'}</span><button type="button" class="teaching-secondary" data-move-index="${i}" data-direction="-1" ${i===0?'disabled':''} aria-label="上移 ${escapeHtml(m.title || m.filename)}">↑ 上移</button><button type="button" class="teaching-secondary" data-move-index="${i}" data-direction="1" ${i===arr.length-1?'disabled':''} aria-label="下移 ${escapeHtml(m.title || m.filename)}">↓ 下移</button></div>`).join('') || '<p class="teaching-help">尚未關聯教材，請先至教材管理加入本課程。</p>';
    if (focusIndex != null) document.querySelector(`[data-move-index="${focusIndex}"][data-direction="${direction}"]:not(:disabled)`)?.focus();
}
async function teachingSaveCourse() {
    if (!teachingEditor || teachingEditorBusy) return;
    const form = document.querySelector('#teaching-dialog form'); if (!form.reportValidity()) return;
    const get = id => document.getElementById('plan-'+id).value;
    const payload = {title:get('title').trim(),desc:get('desc'),learningObjectives:get('objectives'),estimatedMinutes:Number(get('minutes')),sortOrder:Number(get('order')),startDate:get('start'),endDate:get('end'),active:document.getElementById('plan-active').checked,materialOrder:teachingEditor.materials.map(m=>m.id)};
    const status = document.getElementById('plan-status'); status.classList.remove('error');
    if (payload.startDate && payload.endDate && payload.startDate > payload.endDate) {status.classList.add('error');status.textContent='完成日期不可早於開始日期。';return;}
    const key = await getAdminKey(); if (!key) return;
    teachingEditorBusy = true; document.getElementById('teaching-fields').disabled = true; document.getElementById('plan-save').disabled = true; status.textContent = '正在儲存…';
    try {
        const res = await fetch(`/api/courses/${encodeURIComponent(teachingEditor.course.id)}/plan`,{method:'PUT',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});
        const data = await res.json(); if (!res.ok) throw Error(data.error || '儲存失敗');
        teachingEditor.course = data; teachingEditor.dirty = false;
        adminCoursesCache.clear();
        status.textContent = '✓ 課程安排已儲存，學員重新載入教材頁即可看到。';
        await Promise.allSettled([renderAdminCourses(true),renderAdminCourseMaterialHub(true)]);
    } catch (err) {status.classList.add('error');status.textContent='尚未儲存：'+err.message+'。表單內容已保留。';}
    finally {teachingEditorBusy=false;document.getElementById('teaching-fields').disabled=false;document.getElementById('plan-save').disabled=false;}
}
document.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.materialOpen) openMaterial(button.dataset.materialOpen);
    if (button.dataset.materialComplete) {button.disabled=true;markMaterialComplete(button.dataset.materialComplete).finally(()=>{if(button.isConnected)button.disabled=false;});}
    if (button.dataset.moveIndex != null && teachingEditor && !teachingEditorBusy) {
        const index=Number(button.dataset.moveIndex),direction=Number(button.dataset.direction),next=index+direction;
        if(next<0||next>=teachingEditor.materials.length)return;
        [teachingEditor.materials[index],teachingEditor.materials[next]]=[teachingEditor.materials[next],teachingEditor.materials[index]];
        teachingEditor.dirty=true;teachingRenderOrder(next,direction);
        document.getElementById('plan-status').textContent='教材順序已調整，尚未儲存。';
    }
});
document.addEventListener('input', event => {
    if(event.target.closest('#teaching-fields') && teachingEditor) teachingEditor.dirty=true;
    if (['learning-name','learning-empid'].includes(event.target.id)) {
        teachingIdentityRequest++; teachingIdentity=null; myCompletedMaterials={};
        document.getElementById('learning-load').disabled=false;
        const status=document.getElementById('learning-identity-status');
        status.classList.remove('error');status.textContent='身分已變更，請按「載入我的學習紀錄」。';
        renderCourseOverview();
    }
});
window.addEventListener('beforeunload', event => {
    if(teachingEditor?.dirty) {event.preventDefault();event.returnValue='';}
});

function teachingMediaTools(entry) {
    teachingMediaId=entry.id;
    const button=document.getElementById('media-complete');
    button.hidden=!!entry.isBuiltin;
    button.disabled=!!myCompletedMaterials[entry.id];
    button.textContent=button.disabled?'✓ 已完成':'標記完成';
    document.getElementById('media-next').disabled=!teachingFindNextMaterial(entry.id);
}
async function teachingCompleteMedia() {
    const button=document.getElementById('media-complete');
    if(button.disabled)return;
    const id=teachingMediaId; button.disabled=true;
    try {await markMaterialComplete(id);}
    finally {if(id===teachingMediaId){button.disabled=!!myCompletedMaterials[id];button.textContent=button.disabled?'✓ 已完成':'標記完成';}}
}
function teachingNextMedia() {
    const next=teachingFindNextMaterial(teachingMediaId);
    if(next){closeMediaViewer();openMaterial(next.id);}
}
