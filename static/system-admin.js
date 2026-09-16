/* V5.9.0 · 後台內容、題庫、帳號與系統管理 */
let currentReviewRecordIndex=null;
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

async function getAdminKey() {
    // Compatibility header only.  Server-side session RBAC authorizes every
    // request; no ADMIN_KEY is prompted for or persisted in this browser.
    return 'rbac-session';
}

const ADMIN_CACHE_MS = 30000;
const ADMIN_QUIZ_CACHE_MS = 60000;
const ADMIN_COURSE_CACHE_MS = 60000;
let adminMaterialsCache = { data: null, at: 0 };
const adminQuizCategoriesCache = new Map();
const adminCoursesCache = new Map();
function adminScopeKey(area, group){ return `${area || 'internal'}::${group || 'grpBio'}`; }
function setAdminQuizSyncStatus(text, tone='slate'){
    const el=document.getElementById('admin-quiz-sync-status'); if(!el)return;
    const tones={slate:'bg-slate-100 text-slate-500',indigo:'bg-indigo-50 text-indigo-700',emerald:'bg-emerald-50 text-emerald-700',rose:'bg-rose-50 text-rose-700',amber:'bg-amber-50 text-amber-700'};
    el.className=`text-[11px] px-2.5 py-1 rounded-full font-bold ${tones[tone]||tones.slate}`; el.textContent=text;
}
function adminHasExpandedQuestionEditor(box){
    return !!box?.querySelector('[id^="qedit-"]:not(.hidden), textarea[id^="qedit-"]:focus, input[id^="qedit-"]:focus');
}

// ==================================================================
// 管理者後台：組別選單、教材分類選單、考題頁籤與題庫管理
// ==================================================================

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




const adminQuizQuestionCache = {};

function adminPayloadFromQuestionEditor(qId,catId){
    const q=(adminQuizQuestionCache[catId]||[]).find(x=>x.id===qId);if(!q)throw new Error('找不到題目資料');const box=document.getElementById(`qedit-${qId}`);if(!box)throw new Error('找不到編輯區');const get=f=>box.querySelector(`[data-field="${f}"]`),type=get('questionType')?.value||q.questionType||'choice',cfg={...(q.answerConfig||{})},payload={question:(get('question')?.value||'').trim(),questionType:type,difficulty:get('difficulty')?.value||q.difficulty||'standard',imageUrl:q.imageUrl||'',tag:(get('tag')?.value||'').trim(),explanation:(get('explanation')?.value||'').trim(),active:!!get('active')?.checked,answerConfig:cfg};if(!payload.question)throw new Error('題目內容不能空白');
    if(['choice','multi','image','video'].includes(type)){const opts=[...box.querySelectorAll('[data-field^="opt"]')].map(x=>x.value.trim()).filter(Boolean);if(opts.length<2)throw new Error('此題型至少需要 2 個選項');payload.options=opts;if(type==='multi'){const indices=opts.map((_,i)=>get(`multi${i}`)?.checked?i:null).filter(i=>i!==null);if(!indices.length)throw new Error('複選題至少需要一個正確答案');payload.correct=indices[0];payload.answerConfig={...cfg,correctIndices:indices};}else payload.correct=Math.max(0,Math.min(opts.length-1,Number(get('correct')?.value||0)));}else if(type==='true_false'){payload.options=['是','否'];payload.correct=Number(get('trueFalseCorrect')?.value||0);payload.answerConfig={};}else{payload.options=[];payload.correct=0;}
    if(type==='fill'){const arr=(get('fillAnswers')?.value||'').split('|').map(x=>x.trim()).filter(Boolean);if(!arr.length)throw new Error('填空題至少要有一個可接受答案');payload.answerConfig={...cfg,acceptedAnswers:arr,caseSensitive:!!cfg.caseSensitive};}const mediaUrl=(get('mediaUrl')?.value||'').trim();if(mediaUrl)payload.answerConfig={...payload.answerConfig,mediaUrl,pauseAt:Math.max(0,Number(get('pauseAt')?.value||0))};else if(type==='video')throw new Error('影片題請填入影片 / 媒體網址');return payload;
}

const questionActionBusy=new Set();
const questionBulkBusy=new Set();
async function adminBatchQuestionPatch(catId,items,label='儲存題目'){
    const key=await getAdminKey(); if(!key)throw new Error('未輸入管理者金鑰');
    const res=await fetch('/api/quiz-questions/batch',{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({items})});
    const d=await res.json().catch(()=>({})); if(!res.ok)throw new Error(d.error||`${label}失敗`); return d;
}
document.addEventListener('input',e=>{if(e.target?.id?.startsWith('exam-quota-'))updateExamQuotaTotal();});


// ==================================================================

// ==================================================================
// 管理者後台：各組別 Word 匯出範本 (doc_templates) 管理
// 六組皆可由後台上傳 Word 匯出範本；生化組也納入統一管理。
// ==================================================================
let pendingDocTemplateUploadGroup = null;

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

let materialJobsRefreshTimer=null;

function updateQuizWorkspacePresentation(){
    const title=document.querySelector('#admin-quiz-workspace h4'); const desc=document.querySelector('#admin-quiz-workspace h4 + p');
    if(title) title.textContent='📝 題庫與考卷';
    if(desc) desc.textContent='考卷、題庫、AI 出題、出題藍圖與題目分析集中管理；預設顯示考卷。';
    document.querySelectorAll('[data-admin-role="questions-action"],[data-admin-role="exam-action"]').forEach(x=>x.classList.remove('hidden'));
}

let adminUserAccountsCache=[];
const ADMIN_USER_AREA_LABELS={internal:'院內',pgy:'PGY'};
async function renderAdminUserAccounts(){
    const body=document.getElementById('admin-user-accounts-body'),status=document.getElementById('admin-user-status');if(!body)return;body.innerHTML='<tr><td colspan="6" class="p-5 text-center text-slate-400">讀取帳號中…</td></tr>';
    const key=await getAdminKey();if(!key)return;
    try{const r=await fetch('/api/users',{headers:{'X-Admin-Key':key},cache:'no-store'}),rows=await r.json().catch(()=>[]);if(!r.ok)throw new Error(rows.error||'帳號讀取失敗');adminUserAccountsCache=Array.isArray(rows)?rows:[];
        body.innerHTML=adminUserAccountsCache.length?adminUserAccountsCache.map(u=>{const tags=adminProfileTags(u.responsibilityTags),profile=`<div class="mt-1 text-[11px] text-slate-500">${u.professionalTitle?`職稱：${escapeHtml(u.professionalTitle)}`:'職稱：未設定'}</div>${tags.length?`<div class="mt-1 flex flex-wrap gap-1">${tags.map(tag=>`<span class="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700">${escapeHtml(tag)}</span>`).join('')}</div>`:''}`;return `<tr class="${u.active?'':'opacity-55'}"><td class="p-3"><b>${escapeHtml(u.username)}</b><div class="text-slate-500 mt-1">${escapeHtml(u.name)}</div></td><td class="p-3 font-mono">${escapeHtml(u.empId)}</td><td class="p-3"><div>${escapeHtml(adminUserRoleSummary(u))}</div>${profile}</td><td class="p-3">${ADMIN_USER_AREA_LABELS[u.preferredArea]||''} · ${escapeHtml((GROUPS[u.preferredGroup]||GROUPS.grpBio).name)}</td><td class="p-3 text-slate-500">${escapeHtml((u.lastLoginAt||'尚未登入').slice(0,16).replace('T',' '))}</td><td class="p-3"><div class="flex flex-wrap gap-1.5"><button data-username="${escapeHtml(u.username)}" onclick="openAdminUserEditor(this.dataset.username)" class="text-[11px] border border-teal-200 bg-teal-50 text-teal-800 px-2.5 py-1.5 rounded-lg font-bold">編輯人員資料</button><button data-username="${escapeHtml(u.username)}" onclick="resetAdminUserPassword(this.dataset.username)" class="text-[11px] border border-slate-300 bg-white px-2.5 py-1.5 rounded-lg">重設密碼</button><button data-username="${escapeHtml(u.username)}" onclick="toggleAdminUserAccount(this.dataset.username,${u.active?'false':'true'})" class="text-[11px] ${u.active?'text-rose-600 border-rose-200':'text-emerald-700 border-emerald-200'} border bg-white px-2.5 py-1.5 rounded-lg">${u.active?'停用':'啟用'}</button></div></td></tr>`;}).join(''):'<tr><td colspan="6" class="p-5 text-center text-slate-400">尚未建立登入帳號。請使用上方表單建立第一個帳號。</td></tr>';if(status)status.textContent=`共 ${adminUserAccountsCache.length} 個帳號；「主要職稱／額外職責」與系統角色權限分開管理。`;
    }catch(e){adminUserAccountsCache=[];body.innerHTML=`<tr><td colspan="6" class="p-5 text-center text-rose-600">❌ ${escapeHtml(e.message)}</td></tr>`;}
}
async function createAdminUserAccount(){
    const status=document.getElementById('admin-user-status'),key=await getAdminKey();if(!key)return;const payload={username:document.getElementById('admin-user-username')?.value||'',password:document.getElementById('admin-user-password')?.value||'',name:document.getElementById('admin-user-name')?.value||'',empId:document.getElementById('admin-user-empid')?.value||'',role:document.getElementById('admin-user-role')?.value||'student',preferredArea:document.getElementById('admin-user-area')?.value||'internal',preferredGroup:document.getElementById('admin-user-group')?.value||'grpBio',professionalTitle:document.getElementById('admin-user-professional-title')?.value||'',responsibilityTags:adminProfileTags(document.getElementById('admin-user-responsibility-tags')?.value||'')};status.textContent='⏳ 建立帳號中…';
    const r=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)}),d=await r.json().catch(()=>({}));if(!r.ok){status.textContent='❌ '+(d.error||'建立失敗');return;}['admin-user-username','admin-user-password','admin-user-name','admin-user-empid','admin-user-professional-title','admin-user-responsibility-tags'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});status.textContent=`✅ 已建立 ${d.user.name}（${d.user.username}）`;await renderAdminUserAccounts();
}

async function renderAdminPeople(force=false){
    await renderAdminUserAccounts();
    const body=document.getElementById('admin-people-body'),sum=document.getElementById('admin-people-summary');if(!body||!sum)return;body.innerHTML='<tr><td colspan="5" class="p-5 text-center text-slate-400">讀取中…</td></tr>';
    try{const records=await fetchAdminRecords();if(!records)return;const map=new Map();for(const r of records){const k=(r.empId||'')+'|'+(r.name||'');if(!k.replace('|',''))continue;const old=map.get(k)||{name:r.name||'',empId:r.empId||'',role:r.role||'',count:0,last:r.timestamp||''};old.count++;if((r.timestamp||'')>=(old.last||'')){old.last=r.timestamp||'';old.role=r.role||old.role;}map.set(k,old);}const list=[...map.values()].sort((a,b)=>(b.last||'').localeCompare(a.last||''));const roles=new Set(list.map(x=>x.role).filter(Boolean));sum.innerHTML=`<div class="rounded-xl bg-sky-50 border border-sky-100 p-4"><span class="text-xs text-sky-700">近期人員</span><b class="block text-2xl text-sky-950 mt-1">${list.length}</b></div><div class="rounded-xl bg-slate-50 border border-slate-200 p-4"><span class="text-xs text-slate-500">身份類型</span><b class="block text-2xl text-slate-900 mt-1">${roles.size}</b></div><div class="rounded-xl bg-emerald-50 border border-emerald-100 p-4"><span class="text-xs text-emerald-700">考核紀錄</span><b class="block text-2xl text-emerald-950 mt-1">${records.length}</b></div>`;body.innerHTML=list.length?list.map(x=>`<tr><td class="p-3 font-bold">${escapeHtml(x.name)}</td><td class="p-3 font-mono">${escapeHtml(x.empId)}</td><td class="p-3">${escapeHtml(x.role||'—')}</td><td class="p-3">${x.count}</td><td class="p-3 text-slate-500">${escapeHtml(x.last||'')}</td></tr>`).join(''):'<tr><td colspan="5" class="p-5 text-center text-slate-400">尚無考核人員資料</td></tr>';}
    catch(e){body.innerHTML=`<tr><td colspan="5" class="p-5 text-center text-rose-500">❌ ${escapeHtml(e.message)}</td></tr>`;}
}
function systemStatusCard(icon,title,state,detail,tone='slate'){const classes={emerald:'border-emerald-200 bg-emerald-50 text-emerald-900',amber:'border-amber-200 bg-amber-50 text-amber-900',rose:'border-rose-200 bg-rose-50 text-rose-900',slate:'border-slate-200 bg-slate-50 text-slate-900'};return `<div class="rounded-xl border p-4 ${classes[tone]||classes.slate}"><div class="text-sm font-black">${icon} ${escapeHtml(title)}</div><div class="text-xs font-bold mt-2">${escapeHtml(state)}</div><div class="text-[11px] opacity-75 mt-1 break-all">${escapeHtml(detail||'')}</div></div>`;}
async function renderAdminSystemStatus(force=false){const cards=document.getElementById('admin-system-health'),storage=document.getElementById('admin-system-storage');if(!cards||!storage)return;cards.innerHTML='<div class="col-span-full text-xs text-slate-400">檢查服務中…</div>';storage.textContent='讀取儲存狀態中…';const key=await getAdminKey();if(!key)return;try{const [hr,sr,ar]=await Promise.all([fetch('/health'),fetch(`/api/storage-status${force?'?refresh=1':''}`,{headers:{'X-Admin-Key':key}}),fetch('/api/ai-questions/status',{headers:{'X-Admin-Key':key}})]);const h=await hr.json().catch(()=>({})),s=await sr.json().catch(()=>({})),a=await ar.json().catch(()=>({}));const dbOk=!!h.ok;cards.innerHTML=systemStatusCard('🖥️','Render / Web',dbOk?'正常':'異常',h.service||'',dbOk?'emerald':'rose')+systemStatusCard('🗄️','Supabase / Database',dbOk?'可連線':'待確認','健康檢查已通過即表示 Flask 與初始化流程正常',dbOk?'emerald':'amber')+systemStatusCard('🟣','MEGA',s.megaConfigured?(s.megaError?'已設定但檢查失敗':'已設定'):'未設定',s.megaSpace?`${s.megaSpace.usedGb??'?'} / ${s.megaSpace.totalGb??'?'} GB；網站上限 ${s.megaFreeLimitGb||18} GB`:(s.megaError||''),s.megaConfigured&&!s.megaError?'emerald':(s.megaConfigured?'amber':'rose'))+systemStatusCard('🤖','Groq AI',a.configured?'已設定':'未設定',`${a.provider||''} ${a.model||''}`,a.configured?'emerald':'amber');const g=s.gdriveConfigured?(s.gdriveConnected?'✅ Google Drive 備援已連線':((s.activeBackend||s.configuredMode)==='gdrive'?'⚠️ Google Drive 目前使用中，但連線尚未驗證':'ℹ️ Google Drive 備援已設定，尚未執行連線測試（不影響目前主要儲存）')):'○ Google Drive 備援未設定';storage.innerHTML=`<div class="font-black text-slate-900">教材儲存策略</div><div class="mt-2">主要：<b>${escapeHtml(s.activeBackend||s.configuredMode||'')}</b>　｜　備援：<b>${escapeHtml(s.fallbackBackend||'')}</b>　｜　免費模式：<b>${s.megaFreeOnly?'是':'否'}</b></div><div class="mt-2">${g}</div><div class="mt-2 text-xs text-slate-500">MEGA ${s.materials?.mega||0} 份、Google Drive ${s.materials?.gdrive||0} 份、R2 ${s.materials?.r2||0} 份、本機 ${s.materials?.local||0} 份</div>${s.error?`<div class="mt-2 text-rose-600">${escapeHtml(s.error)}</div>`:''}`;}catch(e){cards.innerHTML=systemStatusCard('⚠️','系統狀態','檢查失敗',e.message,'rose');storage.textContent='無法讀取儲存狀態';}}

function difficultyLabel(d){return ({basic:'基礎',standard:'一般',advanced:'進階'})[d||'standard']||'一般';}
let adminResultsPage = 1;
// --- 附件1 匯出功能 (支援後台直接匯出或目前頁籤即時匯出) ---
// 生化組：沿用原本「匯出時於瀏覽器選一次附件1.docx，之後快取沿用」的方式。
// 六組皆優先使用管理者已上傳到伺服器的該組別空白範本，自動抓取並直接填入匯出，
// 不需要每次匯出都手動選檔。
let cachedTemplateBuffer = null;
let adminRecords = [];
let adminKey = '';
let pendingExportRecordIndex = null;
let isExportingCurrentTab = false;

// 組出目前頁籤（作答中）的匯出資料與檔名
// 組出後台某一筆已存檔成績的匯出資料與檔名
// 用給定的範本二進位內容 (ArrayBuffer) 填入資料並下載，成功回傳 true
// 依組別代碼向伺服器抓取該組已上傳的空白範本並直接匯出

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
