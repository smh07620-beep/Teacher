/* V5.9.0 · 共用狀態、身分與組別路由 */
const EVALUATOR_NAME_MEMORY_KEY = 'smh_evaluator_name';
const EVALUATOR_TITLE_MEMORY_KEY = 'smh_evaluator_title';
const EVALUATOR_HISTORY_MEMORY_KEY = 'smh_evaluator_history_v1';
const LEARNER_NAME_MEMORY_KEY = AppCore.memoryKeys.learnerName;
const LEARNER_EMPID_MEMORY_KEY = AppCore.memoryKeys.learnerEmpId;

function readLocalMemory(key) {
    try { return localStorage.getItem(key) || ''; } catch (_) { return ''; }
}

function writeLocalMemory(key, value) {
    try {
        if (value) localStorage.setItem(key, value);
        else localStorage.removeItem(key);
    } catch (_) {}
}

function rememberLearnerFields() {
    const name=(document.getElementById('examinee-name')?.value || document.getElementById('progress-name')?.value || '').trim();
    const empId=(document.getElementById('examinee-id')?.value || document.getElementById('progress-empid')?.value || '').trim();
    if(name) writeLocalMemory(LEARNER_NAME_MEMORY_KEY,name);
    if(empId) writeLocalMemory(LEARNER_EMPID_MEMORY_KEY,empId);
}

function loadRememberedLearnerFields() {
    const name=readLocalMemory(LEARNER_NAME_MEMORY_KEY), empId=readLocalMemory(LEARNER_EMPID_MEMORY_KEY);
    ['examinee-name','progress-name','pgy-assess-name'].forEach(id=>{const el=document.getElementById(id);if(el&&!el.value)el.value=name;});
    ['examinee-id','progress-empid','pgy-assess-empid'].forEach(id=>{const el=document.getElementById(id);if(el&&!el.value)el.value=empId;});
}
function syncLinkedLearnerUI(){
    const name=readLocalMemory(LEARNER_NAME_MEMORY_KEY),empId=readLocalMemory(LEARNER_EMPID_MEMORY_KEY);
    ['examinee-name','progress-name','pgy-assess-name'].forEach(id=>{const el=document.getElementById(id);if(el)el.value=name;});
    ['examinee-id','progress-empid','pgy-assess-empid'].forEach(id=>{const el=document.getElementById(id);if(el)el.value=empId;});
    const display=name||'未設定姓名';
    const set=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v;};
    set('v573-system-user-name',display);set('v573-system-user-id',empId?`工號 ${empId}`:'請回首頁設定');
    set('v573-exam-person-name',display);set('v573-exam-person-id',empId?`工號 ${empId}`:'請先回首頁設定個人資料');
    set('v573-progress-person',empId?`${display}｜工號 ${empId}`:'尚未設定，請回首頁設定個人資料');
    document.getElementById('v573-exam-linked')?.classList.toggle('missing',!empId);
    document.getElementById('v573-progress-linked')?.classList.toggle('missing',!empId);
    return {name,empId};
}
function syncGlobalLearningSearch(value){
    const hidden=document.getElementById('learning-search');if(hidden)hidden.value=value||'';
    if(['materials','atlas','media','troubleshooting','sop'].includes(currentLearningModule) && typeof renderCourseOverview==='function') renderCourseOverview();
}
function handleGlobalLearningSearchKey(event){
    if(event.key!=='Enter')return;event.preventDefault();const q=(event.currentTarget?.value||'').trim();
    if(q.includes('題庫'))return openAdminWorkspace('questions');
    if(q.includes('教師')||q.includes('閱卷')||q.includes('評分'))return openAdminWorkspace('teacher');
    if(q.includes('設定'))return openAdminWorkspace('system');
    if(q.includes('考核')||q.includes('考卷'))return switchLearningModule('exam');
    switchLearningModule('materials');setTimeout(()=>renderCourseOverview(),0);
}

function goBackLearning(){ location.href=currentTrainingArea==='pgy'?'/pgy':'/internal'; }

function getEvaluatorHistory() {
    try {
        const raw = JSON.parse(readLocalMemory(EVALUATOR_HISTORY_MEMORY_KEY) || '[]');
        return Array.isArray(raw) ? raw.filter(x => x && typeof x.name === 'string' && x.name.trim()).slice(0, 20) : [];
    } catch (_) {
        return [];
    }
}

function renderEvaluatorHistory() {
    const list = document.getElementById('evaluator-name-history');
    if (!list) return;
    list.innerHTML = getEvaluatorHistory().map(x => `<option value="${escapeHtml(x.name)}">${escapeHtml(x.title || '')}</option>`).join('');
}

function applyRememberedEvaluatorTitle() {
    const name = document.getElementById('evaluator-name')?.value.trim() || '';
    const titleEl = document.getElementById('evaluator-title');
    if (!name || !titleEl) return;
    const found = getEvaluatorHistory().find(x => x.name === name);
    if (found && found.title) titleEl.value = found.title;
}

function rememberEvaluatorFields() {
    const name = document.getElementById('evaluator-name')?.value.trim() || '';
    const title = document.getElementById('evaluator-title')?.value || '';
    writeLocalMemory(EVALUATOR_NAME_MEMORY_KEY, name);
    writeLocalMemory(EVALUATOR_TITLE_MEMORY_KEY, title);
    if (name) {
        const history = getEvaluatorHistory().filter(x => x.name !== name);
        history.unshift({ name, title });
        writeLocalMemory(EVALUATOR_HISTORY_MEMORY_KEY, JSON.stringify(history.slice(0, 20)));
        renderEvaluatorHistory();
    }
}

function loadRememberedEvaluatorFields() {
    const nameEl = document.getElementById('evaluator-name');
    const titleEl = document.getElementById('evaluator-title');
    if (nameEl) nameEl.value = readLocalMemory(EVALUATOR_NAME_MEMORY_KEY);
    if (titleEl) titleEl.value = readLocalMemory(EVALUATOR_TITLE_MEMORY_KEY);
    renderEvaluatorHistory();
}

// ==================================================================
// 六大組別 (Top-level Groups)
// ==================================================================
const urlParams = new URLSearchParams(window.location.search);
const currentTrainingArea = ["internal","pgy"].includes(urlParams.get("area")) ? urlParams.get("area") : "internal";
const initialGroupFromUrl = urlParams.get("group") || "grpBio";
const initialModuleFromUrl = urlParams.get("module") || "materials";
const trainingAreaLabel = currentTrainingArea === "pgy" ? "PGY訓練區" : "內部教育訓練區";

const GROUPS = AppCore.groups;

function getGroupMemberRole(groupKey = currentGroupKey) {
    const g = (GROUPS[groupKey] || GROUPS.grpBio);
    if(groupKey==='grpNew') return '新進醫檢師';
    if(groupKey==='grpPgyDocs') return 'PGY受訓人員';
    return `${g.name}組員`;
}

function updateLearningBreadcrumb() {
    const a=document.getElementById('learning-area-crumb'); const g=document.getElementById('learning-group-crumb'); const link=document.getElementById('learning-area-link');
    if(a) a.textContent=trainingAreaLabel;
    if(link) link.href=currentTrainingArea==='pgy'?'/pgy':'/internal';
    if(g) g.textContent=(GROUPS[currentGroupKey]||GROUPS.grpBio).name;
}

function updateExamPersonnelRoleOptions() {
    updateLearningBreadcrumb();
    const select = document.getElementById('examinee-role');
    if (!select) return;
    const previous = select.value;
    const memberRole = getGroupMemberRole();
    const wasGroupMember = previous.endsWith('組組員');
    select.innerHTML = `
        <option value="">請選擇類別</option>
        <option value="值班醫檢師">值班醫檢師</option>
        <option value="${memberRole}">${memberRole}</option>
    `;
    if (previous === '值班醫檢師') select.value = previous;
    else if (wasGroupMember) select.value = memberRole;
    const hint = document.getElementById('examinee-role-hint');
    if (hint) hint.textContent = `目前組別：可選「值班醫檢師」或「${memberRole}」。`;
}
let currentGroupKey = 'grpBio';

function renderGroupTabs() { /* V5.3.20：組別在上一層選定，組內不再渲染跨組切換列 */ }

let currentLearningModule = 'materials';
let currentMaterialView = 'materials';
const LEARNING_MODULES = {
    materials:{label:'課程學習中心',icon:'📚',heading:'課程學習中心',desc:'以課程為核心整合教材、圖譜、影片、Troubleshooting、SOP 與課後評量；不必再上下對照不同清單。'},
    atlas:{label:'數位顯微鏡圖庫',icon:'🔬',heading:'數位顯微鏡圖庫',desc:'高解析細胞、細菌、結晶與寄生蟲圖像，支援正／異常對照、Lightbox 與局部放大。'},
    media:{label:'操作教學影片',icon:'🎬',heading:'操作教學影片區',desc:'抽血技術、儀器日常保養、特殊染色與操作步驟；支援全螢幕、音量與播放速度。'},
    exam:{label:'線上測驗',icon:'📝'},
    troubleshooting:{label:'常見錯誤分析',icon:'🧰',heading:'常見錯誤分析（Troubleshooting）',desc:'檢體溶血、檢體量不足、QC 違反 Westgard 規則與儀器異常的處理步驟。'},
    sop:{label:'SOP 閱讀區',icon:'📑',heading:'SOP 站內閱讀區',desc:'SOP 僅供站內閱讀，不提供學員端原始檔下載；請由管理者後台維護版本。'},
    progress:{label:'訓練進度',icon:'📈'},
    assessment:{label:'PGY 評量中心',icon:'🧭'}
};
function updateLearningModuleNav(){
    const g=GROUPS[currentGroupKey]||GROUPS.grpBio;
    const h=document.getElementById('module-hub-heading'); if(h) h.textContent=`${g.name}｜學習路徑`;
    const chip=document.getElementById('module-area-chip'); if(chip) chip.textContent=trainingAreaLabel;
    const assessmentBtn=document.getElementById('pgy-assessment-hub-btn');
    assessmentBtn?.classList.toggle('hidden', currentTrainingArea!=='pgy');
    assessmentBtn?.classList.toggle('active',currentLearningModule==='assessment');
    Object.keys(LEARNING_MODULES).forEach(k=>document.getElementById(`module-btn-${k}`)?.classList.toggle('active',k===currentLearningModule));
    const resources=document.getElementById('v580-resource-drawer');
    if(resources&&['atlas','media','troubleshooting','sop'].includes(currentLearningModule)) resources.open=true;
}
const GROUP_SPECIALTY = {
    grpMicro:{atlas:[['💎','尿液沉渣結晶辨識','建立尿沉渣結晶高解析圖庫，支援正／異常與易混淆型態對照。'],['🪱','寄生蟲蟲卵 / 原蟲辨識','集中整理蟲卵、原蟲與重要形態特徵，適合圖像辨識訓練。']]},
    grpHema:{atlas:[['🩸','血球型態識別圖庫','RBC / WBC / Platelet morphology、異常白血球與紅血球變異對照。']]},
    grpBB:{troubleshooting:[['🩸','輸血反應案例分析','整理發燒、過敏、溶血、TRALI / TACO 與 Discrepancy 案例的判讀與處置。']]},
    grpBact:{atlas:[['🦠','細菌 / 真菌形態圖庫','建立染色型態、菌落或顯微影像辨識資料庫，搭配圖像辨識訓練。']]}
};
function renderSpecialtyFocus(){
    const zone=document.getElementById('specialty-focus-zone'); if(!zone)return;
    const items=(GROUP_SPECIALTY[currentGroupKey]||{})[currentMaterialView]||[];
    if(!items.length){zone.classList.add('hidden');zone.innerHTML='';return;}
    zone.classList.remove('hidden');
    zone.innerHTML=`<div class="flex items-center justify-between gap-3 mb-3"><div><p class="edu-kicker">SPECIALTY FOCUS</p><h3 class="font-black text-slate-900 mt-1">${escapeHtml((GROUPS[currentGroupKey]||GROUPS.grpBio).name)}｜專業辨識專區</h3></div><span class="specialty-chip">本組重點</span></div><div class="grid md:grid-cols-2 gap-3">${items.map(x=>`<div class="rounded-xl border border-slate-200 bg-white p-4"><div class="text-2xl">${x[0]}</div><div class="font-black text-slate-800 mt-2">${escapeHtml(x[1])}</div><p class="text-xs text-slate-500 mt-1 leading-5">${escapeHtml(x[2])}</p></div>`).join('')}</div>`;
}
function applyMaterialModulePresentation(){
    const cfg=LEARNING_MODULES[currentMaterialView]||LEARNING_MODULES.materials;
    const g=GROUPS[currentGroupKey]||GROUPS.grpBio;
    const heading=document.getElementById('slides-panel-heading');
    const desc=document.getElementById('slides-panel-desc');
    const steps=document.getElementById('slides-learning-steps');
    if(heading) heading.textContent=`${cfg.icon} ${g.name}${cfg.heading}`;
    if(desc) desc.textContent=cfg.desc;
    if(steps) steps.classList.toggle('hidden',currentMaterialView!=='materials');
    renderSpecialtyFocus();
}
function switchLearningModule(module){
    if(!LEARNING_MODULES[module]) module='materials';
    if(module==='assessment' && currentTrainingArea!=='pgy') module='materials';
    currentLearningModule=module;
    if(['materials','atlas','media','troubleshooting','sop'].includes(module)) currentMaterialView=module;
    const panel=module==='exam'?'exam':(module==='progress'?'progress':(module==='assessment'?'assessment':'slides'));
    const panels={slides:document.getElementById('panel-slides'),exam:document.getElementById('panel-exam'),progress:document.getElementById('panel-progress'),assessment:document.getElementById('panel-assessment')};
    Object.entries(panels).forEach(([k,el])=>el&&el.classList.toggle('hidden',k!==panel));
    updateLearningModuleNav();
    if(panel==='slides'){applyMaterialModulePresentation();renderSlidesGrid();}
    if(panel==='assessment'){ initPgyAssessmentCenter(); }
    if(panel==='progress'){
        const identity=syncLinkedLearnerUI();
        if(identity.name&&identity.empId) setTimeout(()=>loadMyProgress(),0);
        else document.getElementById('progress-summary')?.classList.add('hidden');
    }
    window.scrollTo({top:0,behavior:'smooth'});
}

// 切換組別：同時刷新目前所在的投影片區 / 考試區內容
function switchGroup(groupKey) {
    if (!GROUPS[groupKey]) groupKey = 'grpBio';
    currentGroupKey = groupKey;
    const areaLabelEl=document.getElementById("area-banner-label"); if(areaLabelEl) areaLabelEl.textContent=trainingAreaLabel;
    updateExamPersonnelRoleOptions();
    updateLearningModuleNav();

    const bioExamTabs = document.getElementById('bio-exam-tabs');
    const dynamicExamTabs = document.getElementById('dynamic-exam-tabs');
    const slidesHeading = document.getElementById('slides-panel-heading');
    applyMaterialModulePresentation();
    if (bioExamTabs) bioExamTabs.classList.add('hidden');
    if (dynamicExamTabs) dynamicExamTabs.classList.remove('hidden');
    currentCatKey = '';
    renderDynamicExamTabs();

    if (!document.getElementById('panel-slides').classList.contains('hidden')) renderSlidesGrid();
}

// ==================================================================
// 教育訓練教材區 (Training Slides Zone) — 由後端 Flask API 提供
// ==================================================================
// 簡報清單、上傳、自動轉檔全部交給後端 /api/slides 系列端點處理，
// 前端只負責顯示與呼叫 API，因此使用者上傳的 PPTX 也能跟內建簡報一樣
// 直接在頁面內逐頁瀏覽，不需下載檔案。
