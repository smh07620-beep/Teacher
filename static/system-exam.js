/* V5.9.0 · 線上考核與答題流程 */
function renumberQuestions(questions) {
    return questions.map((q, idx) => ({ ...q, id: idx + 1 }));
}

// V5.3.7：六組（包含原本生化組四份考卷）全部由資料庫動態載入。
const allQuizData = {};
let currentCatKey = '';
let isSubmittedMap = {};
let userAnswersMap = {};
let flaggedQuestionsMap = {};
let questionTimingMap = {};
let questionTimingObserver = null;
let chartInstance = null;

// ==================================================================
// 六組考卷皆使用動態考題頁籤 / 題目 —— 全部由後台管理者建立與維護，
// 前端只負責讀取 /api/quiz-categories 與 /api/quiz-questions 並渲染。
// ==================================================================
let dynamicCategoriesCache = {}; // { 'area:group': [ {id,title,desc,...}, ... ] }
let blindTestMode = false;

// V5.4.0：考卷摘要；作答與計分由伺服器 attempt 流程唯一負責。
function examBankCount(c){ return Math.max(0, Number(c?.questionCount || 0)); }
function examQuotaTotal(c){const r=c?.drawRules||{},q=r?.quotas||{};return r?.mode==='type_quota'?['choice','multi','true_false','fill','essay','image','video'].reduce((s,k)=>s+Math.max(0,Number(q[k]||0)),0):0;}
function examActualCount(c){ const bank=examBankCount(c), quota=examQuotaTotal(c), draw=Math.max(0,Number(c?.drawCount||0)); return quota>0?Math.min(quota,bank):(draw>0?Math.min(draw,bank):bank); }
function examDrawLabel(c){ const quota=examQuotaTotal(c),draw=Math.max(0,Number(c?.drawCount||0)), bank=examBankCount(c); return quota>0?`依題型配額 ${Math.min(quota,bank||quota)} 題`:(draw>0?`隨機抽 ${Math.min(draw,bank||draw)} 題`:'全部啟用題目'); }
function examAudienceLabel(c){ return String(c?.audience||'所有符合課程資格人員').trim() || '所有符合課程資格人員'; }
function examDraftKey(catId){ return `v540-exam-draft:${currentTrainingArea}:${currentGroupKey}:${catId}`; }
const secureAttemptMap = {};
const secureAttemptLoadMap = {};
function secureDraftKey(catId){return `v630-secure-exam:${currentTrainingArea}:${currentGroupKey}:${catId}`;}
function purgeLegacyDraft(catId){try{localStorage.removeItem(examDraftKey(catId));}catch(_e){}}
function loadExamDraft(catId){
    purgeLegacyDraft(catId);
    try{const raw=localStorage.getItem(secureDraftKey(catId));if(!raw)return null;const d=JSON.parse(raw);return d&&d.version===2&&d.attemptId&&Array.isArray(d.answers)?d:null;}catch(_e){return null;}
}
function saveExamDraft(catId=currentCatKey){
    if(!catId||isSubmittedMap[catId]||!allQuizData[catId]||!secureAttemptMap[catId])return;
    try{localStorage.setItem(secureDraftKey(catId),JSON.stringify({version:2,attemptId:secureAttemptMap[catId],savedAt:new Date().toISOString(),answers:userAnswersMap[catId]||[],flags:flaggedQuestionsMap[catId]||[],timings:questionTimingSeconds(catId)}));}catch(_e){}
}
function clearExamDraft(catId=currentCatKey){try{if(catId){localStorage.removeItem(secureDraftKey(catId));localStorage.removeItem(examDraftKey(catId));}}catch(_e){}}
function hasExamDraft(catId){
    const d=loadExamDraft(catId);
    if(!d || !Array.isArray(d.answers)) return false;
    return d.answers.some(a => Array.isArray(a) ? a.length>0 : (a!==null && a!==undefined && String(a).trim()!==''));
}
function normalizePublicQuestion(q){
    return {
        id:q.id,
        questionId:q.id,
        category:q.tag||q.category||'一般',
        tag:q.tag||q.category||'一般',
        question:q.question,
        questionType:q.questionType||'choice',
        imageUrl:q.imageUrl||'',
        options:Array.isArray(q.options)?q.options:[],
        answerConfig:q.answerConfig&&typeof q.answerConfig==='object'?q.answerConfig:{},
        reviewSource:q.reviewSource&&typeof q.reviewSource==='object'?q.reviewSource:{}
    };
}
async function secureExamApi(path,options={}){
    const core=window.AppCore||{};
    if(typeof core.api==='function')return core.api(path,options);
    let response;
    try{response=await fetch(path,{credentials:'same-origin',...options});}
    catch(cause){const error=new Error('無法連線到伺服器，請檢查網路後再試。');error.status=0;error.code='NETWORK_ERROR';error.cause=cause;throw error;}
    const data=await response.json().catch(()=>({}));
    if(!response.ok){const detail=data?.errorDetail||{},error=new Error(detail.message||data?.error||`請求失敗（${response.status}）`);error.status=response.status;error.code=detail.code||'';error.data=data;error.retryAfter=Number(data?.retryAfter||response.headers.get('retry-after')||0);error.loginRequired=Boolean(response.status===401||data?.loginRequired);throw error;}
    return data;
}
function resetExamAttemptState(catId=currentCatKey){
    if(!catId)return;
    clearExamDraft(catId);
    delete secureAttemptMap[catId];
    delete secureAttemptLoadMap[catId];
    delete allQuizData[catId];
    delete userAnswersMap[catId];
    delete flaggedQuestionsMap[catId];
    delete questionTimingMap[catId];
    delete isSubmittedMap[catId];
}

async function renderDynamicExamTabs() {
    const listBox=document.getElementById('dynamic-exam-tabs-list'),emptyBox=document.getElementById('dynamic-exam-tabs-empty');
    listBox.innerHTML='<p class="text-xs text-slate-400">載入課程考卷中…</p>';emptyBox.classList.add('hidden');
    try{
        const [res,courseRes]=await Promise.all([fetch(`/api/quiz-categories?group=${currentGroupKey}&area=${currentTrainingArea}`),fetch(`/api/courses?area=${encodeURIComponent(currentTrainingArea)}&group=${encodeURIComponent(currentGroupKey)}`)]);
        const cats=await res.json();if(courseRes.ok)cachedCourses=await courseRes.json();cachedQuizCategories=Array.isArray(cats)?cats:[];dynamicCategoriesCache[`${currentTrainingArea}:${currentGroupKey}`]=cachedQuizCategories;
        if(!cachedQuizCategories.length){listBox.innerHTML='';emptyBox.classList.remove('hidden');document.getElementById('current-quiz-title').innerHTML=`<span class="text-teal-600">📝</span> ${GROUPS[currentGroupKey].label} 尚無考題`;document.getElementById('current-quiz-desc').innerText='本組別尚未建立任何考卷，請由管理者後台新增。';document.getElementById('quiz-questions-list').innerHTML='';document.getElementById('quick-jump-grid').innerHTML='';document.getElementById('stat-progress').innerText='0 / 0';document.getElementById('stat-flagged').innerText='0 題';const pctText=document.getElementById('exam-progress-percent');if(pctText)pctText.textContent='0%';const pctBar=document.getElementById('exam-progress-bar');if(pctBar)pctBar.style.width='0%';document.getElementById('result-dashboard').classList.add('hidden');return;}
        const courseMap=Object.fromEntries((cachedCourses||[]).map(c=>[c.id,c])),courseOrder=(cachedCourses||[]).map(c=>c.id),grouped={};
        cachedQuizCategories.forEach(c=>{const key=c.courseId&&courseMap[c.courseId]?c.courseId:'__orphan__';(grouped[key]||(grouped[key]=[])).push(c);});
        const keys=[...courseOrder.filter(k=>grouped[k]?.length),...(grouped.__orphan__?['__orphan__']:[])];
        listBox.innerHTML=keys.map(k=>{const course=k==='__orphan__'?null:courseMap[k],items=grouped[k]||[];const desc=course?.desc&&course.desc.trim()!==course.title?.trim()?`<div class="text-[11px] text-slate-500 mt-1">${escapeHtml(course.desc)}</div>`:'';return `<section class="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 sm:p-4"><div class="flex items-start justify-between gap-3 mb-3"><div><div class="text-sm font-black text-slate-800">${course?`📘 ${escapeHtml(course.title)}`:'📁 通用考卷'}</div>${desc}</div><span class="text-[11px] font-bold text-slate-500 bg-white border border-slate-200 rounded-full px-2.5 py-1">考卷 ${items.length} 份</span></div><div class="grid md:grid-cols-2 xl:grid-cols-3 gap-2.5">${items.map(c=>{const bank=examBankCount(c),actual=examActualCount(c),draft=hasExamDraft(c.id);return `<button type="button" data-csp-click="switchDynamicCategory('${c.id}')" id="dyn-tab-${c.id}" class="tab-btn text-left rounded-xl border border-slate-200 bg-white hover:border-teal-300 hover:shadow-sm p-3 transition-all"><div class="flex items-start justify-between gap-2"><span class="font-black text-sm text-slate-900">📝 ${escapeHtml(c.title)}</span>${draft?'<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">可續答</span>':''}</div><div class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-500"><span>👤 ${escapeHtml(examAudienceLabel(c))}</span><span>🎯 及格 ${Number(c.passingScore||80)} 分</span><span>🧠 題庫 ${bank} 題</span><span>📋 本次 ${actual} 題</span></div><div class="mt-2 text-[11px] font-bold text-teal-700">${escapeHtml(examDrawLabel(c))} → ${draft?'繼續作答':'開始考核'}</div></button>`;}).join('')}</div></section>`;}).join('');
        const requestedExamId=new URLSearchParams(window.location.search).get('examId')||'';
        const requestedCategory=cachedQuizCategories.find(
            c=>String(c.id)===String(requestedExamId)
        );

        // A learner must deliberately choose an exam unless a valid, explicit
        // examId was supplied (for example from a pending-exam notification).
        // Never fall back to the first category: it can accidentally create an
        // attempt for an unrelated exam.
        const initialCategory = requestedCategory || null;
        if (!initialCategory) {
            currentCatKey='';
            document.getElementById('current-quiz-title').innerHTML='<span class="text-teal-600">📝</span> 請選擇考卷';
            document.getElementById('current-quiz-desc').innerText=requestedExamId?'找不到指定的考卷，請從清單選擇。':'請從上方清單選擇要開始的考卷。';
            document.getElementById('quiz-questions-list').innerHTML='';
            document.getElementById('quick-jump-grid').innerHTML='';
            document.getElementById('stat-progress').innerText='0 / 0';
            document.getElementById('stat-flagged').innerText='0 題';
            const pctText=document.getElementById('exam-progress-percent');if(pctText)pctText.textContent='0%';
            const pctBar=document.getElementById('exam-progress-bar');if(pctBar)pctBar.style.width='0%';
            document.getElementById('result-dashboard').classList.add('hidden');
            return;
        }

        await switchDynamicCategory(initialCategory.id);

        if(requestedCategory){
            requestAnimationFrame(()=>{
                const tab=document.getElementById(
                    `dyn-tab-${requestedCategory.id}`
                );

                tab?.scrollIntoView({
                    behavior:'smooth',
                    block:'nearest'
                });
            });
        }
    }catch(err){console.error(err);listBox.innerHTML='<p class="text-xs text-rose-500">❌ 讀取考卷失敗</p>';}
}

async function ensureDynamicCategoryLoaded(catId) {
    if(allQuizData[catId])return;
    if(secureAttemptLoadMap[catId])return secureAttemptLoadMap[catId];
    const load=(async()=>{
        const cats=dynamicCategoriesCache[`${currentTrainingArea}:${currentGroupKey}`]||[],catMeta=cats.find(c=>c.id===catId)||{};
        let draft=loadExamDraft(catId),attempt=null;
        if(draft?.attemptId){
            try{attempt=await secureExamApi(`/api/exam-attempts/${encodeURIComponent(draft.attemptId)}`);}
            catch(error){if([404,409,410].includes(error.status)){clearExamDraft(catId);draft=null;}else throw error;}
        }
        if(!attempt){attempt=await secureExamApi('/api/exam-attempts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quizCategoryId:catId})});draft=null;}
        secureAttemptMap[catId]=attempt.attemptId;
        const normalized=renumberQuestions((attempt.questions||[]).map(normalizePublicQuestion));
        const passingScore=Math.max(1,Math.min(100,Number(attempt.passingScore||catMeta.passingScore||80))),audience=examAudienceLabel(catMeta),baseDesc=(catMeta.desc||'').trim();
        allQuizData[catId]={title:attempt.quizTitle||catMeta.title||'考卷',desc:`${baseDesc?baseDesc+' · ':''}適用：${audience} · 本次 ${normalized.length} 題 · 及格 ${passingScore} 分`,courseId:attempt.courseId||catMeta.courseId||'',blindMode:!!catMeta.blindMode,passingScore,drawCount:Math.max(0,Number(catMeta.drawCount||0)),drawRules:catMeta.drawRules||{},audience,evaluatorName:attempt.evaluatorName||'',evaluatorTitle:attempt.evaluatorTitle||'',questions:normalized};
        userAnswersMap[catId]=draft?.answers?.length===normalized.length?draft.answers:new Array(normalized.length).fill(null);
        flaggedQuestionsMap[catId]=draft?.flags?.length===normalized.length?draft.flags:new Array(normalized.length).fill(false);
        const savedTimings=Array.isArray(draft?.timings)&&draft.timings.length===normalized.length?draft.timings:new Array(normalized.length).fill(0);
        questionTimingMap[catId]=savedTimings.map(value=>({elapsedMs:Math.max(0,Number(value||0))*1000,visibleSince:null}));
        isSubmittedMap[catId]=false;
        saveExamDraft(catId);
    })();
    secureAttemptLoadMap[catId]=load;
    try{return await load;}
    finally{if(secureAttemptLoadMap[catId]===load)delete secureAttemptLoadMap[catId];}
}

async function switchDynamicCategory(catId) {
    await ensureDynamicCategoryLoaded(catId);currentCatKey=catId;blindTestMode=!!allQuizData[catId]?.blindMode;
    document.querySelectorAll('#dynamic-exam-tabs-list .tab-btn').forEach(btn=>{const active=btn.id===`dyn-tab-${catId}`;btn.classList.toggle('ring-2',active);btn.classList.toggle('ring-teal-500',active);btn.classList.toggle('border-teal-400',active);btn.classList.toggle('bg-teal-50',active);});updateUIForActiveKey();
}


// 舊版生化頁籤函式保留相容：實際轉交動態考卷。
function switchCategory(catKey) {
    if (catKey === 'zoneA') return switchDynamicCategory('subA1');
    return switchDynamicCategory(catKey);
}
function switchSubCategory(subKey) { return switchDynamicCategory(subKey); }

function updateUIForActiveKey() {
    const catData = allQuizData[currentCatKey];
    document.getElementById('current-quiz-title').innerHTML = `<span class="text-teal-600">📝</span> ${catData.title}`;
    document.getElementById('current-quiz-desc').innerText = catData.desc;
    const evaluatorSummary=document.getElementById('exam-evaluator-summary');
    if(evaluatorSummary){
        const identity=[catData.evaluatorName,catData.evaluatorTitle].filter(Boolean).join(' · ');
        evaluatorSummary.textContent=identity?`考核審核人員：${identity}（由教師審核紀錄自動帶入）`:'此考卷尚未留下可顯示的審核人員資料；成績仍會依伺服器紀錄保存。';
    }

    if (isSubmittedMap[currentCatKey]) {
        document.getElementById('result-dashboard').classList.remove('hidden');
    } else {
        document.getElementById('result-dashboard').classList.add('hidden');
    }

    renderQuickJumpGrid();
    renderQuestions();
    bindVideoQuestionTimeHandlers();
    installQuestionTimingObserver();
    updateProgressStats();
}

// --- Render Quick Jump Navigation Buttons ---
function renderQuickJumpGrid() {
    const container = document.getElementById('quick-jump-grid');
    container.innerHTML = '';
    const questions = allQuizData[currentCatKey].questions;

    questions.forEach((_, index) => {
        const btn = document.createElement('button');
        btn.id = `jump-btn-${index}`;
        btn.onclick = () => scrollToQuestion(index);
        btn.className = 'w-9 h-9 rounded-xl text-xs font-black border transition-all flex items-center justify-center bg-white border-slate-300 text-slate-700 hover:bg-slate-100 hover:border-slate-400';
        btn.innerText = index + 1;
        container.appendChild(btn);
    });
}

function updateQuickJumpButtons() {
    const userAnswers = userAnswersMap[currentCatKey];
    const flaggedQuestions = flaggedQuestionsMap[currentCatKey];
    const questions = allQuizData[currentCatKey].questions;

    questions.forEach((_, index) => {
        const btn = document.getElementById(`jump-btn-${index}`);
        if (!btn) return;

        const isAnswered = answerHasValue(userAnswers[index]);
        const isFlagged = flaggedQuestions[index];

        if (isFlagged) {
            btn.className = 'w-9 h-9 rounded-xl text-xs font-black border transition-all flex items-center justify-center bg-amber-500 text-white border-amber-600 shadow-sm';
        } else if (isAnswered) {
            btn.className = 'w-9 h-9 rounded-xl text-xs font-black border transition-all flex items-center justify-center bg-teal-600 text-white border-teal-700 shadow-sm';
        } else {
            btn.className = 'w-9 h-9 rounded-xl text-xs font-black border transition-all flex items-center justify-center bg-white border-slate-300 text-slate-700 hover:bg-slate-100 hover:border-slate-400';
        }
    });
}

// --- Render All Questions for Active Category ---
function questionTypeLabel(t){return ({choice:'單選題',multi:'複選題',true_false:'是非題',fill:'填空題',essay:'問答題',image:'圖片判讀題',video:'影片題'})[t||'choice']||'單選題';}
function answerHasValue(v){return Array.isArray(v)?v.length>0:(v!==null&&v!==''&&v!==undefined);}
function renderQuestionMedia(q,i,submitted=false){
    if(q.imageUrl)return `<div class="question-media"><button type="button" data-csp-click="openQuestionImage('${escapeHtml(q.imageUrl)}','${escapeHtml(q.question)}')" class="w-full"><img src="${escapeHtml(q.imageUrl)}" alt="題目影像" loading="lazy" decoding="async"><span class="block text-[11px] text-white/70 bg-black/50 py-1">🔍 點擊放大影像，支援局部縮放</span></button></div>`;
    const u=q.answerConfig?.mediaUrl||'';const sec=Number(q.answerConfig?.pauseAt||0);
    if(u)return `<div class="question-media"><video id="question-video-${i}" src="${escapeHtml(u)}" controls playsinline preload="metadata" ${(!submitted&&sec>0)?`data-question-pause-at="${sec}" data-question-index="${i}"`:''}></video>${sec>0?`<div id="video-cue-${i}" class="px-3 py-2 bg-slate-900 text-white/80 text-xs">⏱️ 互動影片題：播放至 ${formatSeconds(sec)} 時會自動暫停並開放作答。</div>`:''}</div>`;
    return '';
}
function formatSeconds(sec){sec=Math.max(0,Math.round(Number(sec)||0));return `${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`;}
function handleVideoQuestionTime(i,video,pauseAt){if(!video||video.dataset.questionUnlocked==='1')return;if(video.currentTime+0.15>=Number(pauseAt||0)){video.dataset.questionUnlocked='1';video.pause();const answer=document.getElementById(`video-answer-${i}`);answer?.classList.remove('hidden');const cue=document.getElementById(`video-cue-${i}`);if(cue){cue.textContent='✅ 已到達指定學習節點，請完成下方題目後再繼續播放。';cue.className='px-3 py-2 bg-teal-900 text-teal-50 text-xs font-bold';}answer?.scrollIntoView({behavior:'smooth',block:'nearest'});}}
function bindVideoQuestionTimeHandlers(){
    document.querySelectorAll('#quiz-questions-list video[data-question-pause-at]').forEach(video=>{
        if(video.dataset.questionTimeBound==='1')return;
        video.dataset.questionTimeBound='1';
        video.addEventListener('timeupdate',()=>handleVideoQuestionTime(Number(video.dataset.questionIndex||0),video,Number(video.dataset.questionPauseAt||0)));
    });
}
function renderQuestions(){const c=document.getElementById('quiz-questions-list');c.innerHTML='';const quizList=allQuizData[currentCatKey].questions,userAnswers=userAnswersMap[currentCatKey],flags=flaggedQuestionsMap[currentCatKey],submitted=isSubmittedMap[currentCatKey];quizList.forEach((q,i)=>{const type=q.questionType||'choice',ans=userAnswers[i];const card=document.createElement('div');card.id=`question-card-${i}`;card.className=submitted?'bg-slate-50/60 p-5 sm:p-6 rounded-2xl border-2 border-slate-300 shadow-sm space-y-4 scroll-mt-24':'question-card-learning micro-card bg-white p-5 sm:p-6 border space-y-4 scroll-mt-28';let body='';if(type==='essay'){body=`<textarea ${submitted?'disabled':''} data-csp-input="selectEssay(${i},this.value)" rows="7" class="w-full min-h-[190px] border border-slate-300 rounded-2xl p-4 text-sm leading-7" placeholder="請在此完整填寫作答內容……">${escapeHtml(typeof ans==='string'?ans:'')}</textarea><p class="text-xs text-slate-400">問答題由考核者人工閱卷。</p>`;}else if(type==='fill'){body=`<input ${submitted?'disabled':''} value="${escapeHtml(typeof ans==='string'?ans:'')}" data-csp-input="selectFill(${i},this.value)" class="fill-answer" placeholder="請輸入答案"><p class="text-xs text-slate-400">請依題意填入關鍵字或數值。</p>`;}else{(q.options||[]).forEach((opt,j)=>{const chosen=type==='multi'?(Array.isArray(ans)&&ans.includes(j)):ans===j;let cls='hover:bg-slate-50 cursor-pointer';if(submitted)cls=chosen?'border-2 border-teal-400 bg-teal-50 font-bold':'opacity-60 bg-slate-50';body+=`<label class="choice-learning flex items-start gap-3 p-4 border ${cls}"><input type="${type==='multi'?'checkbox':'radio'}" ${type==='multi'?'class="multi-check mt-1"':'class="mt-1"'} name="question-${i}" ${chosen?'checked':''} ${submitted?'disabled':''} data-csp-change="${type==='multi'?`selectMulti(${i},${j},this.checked)`:`selectOption(${i},${j})`}"><span class="text-sm font-medium"><b class="mr-1">${String.fromCharCode(65+j)}.</b>${escapeHtml(opt)}</span></label>`;});}const videoLocked=!!q.answerConfig?.mediaUrl&&Number(q.answerConfig?.pauseAt||0)>0&&!submitted&&!answerHasValue(ans);card.innerHTML=`<div class="flex flex-wrap justify-between gap-2 border-b border-slate-100 pb-3"><div class="flex items-center gap-2 flex-wrap"><span class="w-8 h-8 rounded-lg bg-[#0b3342] text-white flex items-center justify-center font-black">${i+1}</span>${blindTestMode?'':`<span class="text-xs font-bold px-2.5 py-1 rounded-full bg-teal-100 text-teal-800">${escapeHtml(q.category||q.tag||'一般')}</span>`}<span class="question-type-pill ${type==='multi'?'bg-violet-100 text-violet-800':type==='fill'?'bg-sky-100 text-sky-800':type==='essay'?'bg-amber-100 text-amber-800':'bg-slate-100 text-slate-600'}">${q.answerConfig?.mediaUrl?'影片・':''}${questionTypeLabel(type)}</span><span id="answer-status-${i}" class="answer-status-pill ${answerHasValue(ans)?'answered':'unanswered'}">${answerHasValue(ans)?'✓ 已作答':'○ 未作答'}</span></div><button data-csp-click="toggleFlag(${i})" id="flag-btn-${i}" class="text-xs px-2.5 py-1 rounded-lg border border-slate-200">${flags[i]?'🚩 取消標記':'🏳️ 標記此題'}</button></div>${renderQuestionMedia(q,i,submitted)}<div id="video-answer-${i}" class="${videoLocked?'hidden ':''}space-y-4"><h3 class="text-base sm:text-lg font-black leading-relaxed">${escapeHtml(q.question)}</h3><div class="space-y-2.5">${body}</div></div>`;c.appendChild(card);});const b=document.getElementById('submit-btn');if(submitted){b.disabled=true;b.className='w-full sm:w-auto bg-slate-400 text-white font-bold px-8 py-3 rounded-xl shadow cursor-not-allowed';b.textContent='🔒 本分頁考卷已繳交';}else{b.disabled=false;b.className='w-full sm:w-auto bg-amber-600 hover:bg-amber-500 text-white font-bold px-8 py-3 rounded-xl shadow-lg';b.textContent='📋 提交試卷結算成績';}updateQuickJumpButtons();}

function questionTimingSeconds(catId=currentCatKey){
    const now=performance.now(),states=questionTimingMap[catId]||[];
    return states.map(state=>Math.round(Math.max(0,(Number(state?.elapsedMs||0)+(state?.visibleSince!=null?now-state.visibleSince:0))/1000)*10)/10);
}
function installQuestionTimingObserver(){
    questionTimingObserver?.disconnect?.(); questionTimingObserver=null;
    if(isSubmittedMap[currentCatKey]||!('IntersectionObserver' in window))return;
    const catId=currentCatKey,states=questionTimingMap[catId]||[];
    questionTimingObserver=new IntersectionObserver(entries=>{
        const now=performance.now();
        entries.forEach(entry=>{
            const index=Number(String(entry.target.id||'').replace('question-card-',''));
            const state=states[index]; if(!state)return;
            if(entry.isIntersecting&&entry.intersectionRatio>=0.5){if(state.visibleSince==null)state.visibleSince=now;}
            else if(state.visibleSince!=null){state.elapsedMs+=Math.max(0,now-state.visibleSince);state.visibleSince=null;}
        });
    },{threshold:[0,0.5,1]});
    document.querySelectorAll('#quiz-questions-list [id^="question-card-"]').forEach(card=>questionTimingObserver.observe(card));
}
function openQuestionImage(url,title){const f={id:'question-image',title:title||'題目影像',filename:'image',viewUrl:url,viewerMode:'image',desc:'題目影像判讀'};cachedSlidesList.push(f);openAtlas('question-image');setTimeout(()=>{cachedSlidesList=cachedSlidesList.filter(x=>x!==f)},10);}
function selectMulti(i,j,checked){if(isSubmittedMap[currentCatKey])return;let a=Array.isArray(userAnswersMap[currentCatKey][i])?[...userAnswersMap[currentCatKey][i]]:[];if(checked&&!a.includes(j))a.push(j);if(!checked)a=a.filter(x=>x!==j);userAnswersMap[currentCatKey][i]=a;saveExamDraft();updateProgressStats();updateQuickJumpButtons();updateAnswerStatus(i);}
function selectFill(i,v){if(isSubmittedMap[currentCatKey])return;userAnswersMap[currentCatKey][i]=v;saveExamDraft();updateProgressStats();updateQuickJumpButtons();updateAnswerStatus(i);}

function selectOption(qIndex, optIndex) {
    if (isSubmittedMap[currentCatKey]) return;
    userAnswersMap[currentCatKey][qIndex] = optIndex;
    saveExamDraft();
    updateProgressStats();
    updateQuickJumpButtons();
    updateAnswerStatus(qIndex);
}

function selectEssay(qIndex, value) {
    if (isSubmittedMap[currentCatKey]) return;
    userAnswersMap[currentCatKey][qIndex] = value;
    saveExamDraft();
    updateProgressStats(); updateQuickJumpButtons(); updateAnswerStatus(qIndex);
}

function toggleFlag(qIndex) {
    if (isSubmittedMap[currentCatKey]) return;
    flaggedQuestionsMap[currentCatKey][qIndex] = !flaggedQuestionsMap[currentCatKey][qIndex];
    saveExamDraft();
    const flagBtn = document.getElementById(`flag-btn-${qIndex}`);
    const isFlagged = flaggedQuestionsMap[currentCatKey][qIndex];
    if (flagBtn) {
        flagBtn.innerHTML = `<span>${isFlagged ? '🚩' : '🏳️'}</span><span>${isFlagged ? '取消標記' : '標記此題'}</span>`;
    }
    updateProgressStats();
    updateQuickJumpButtons();
}

function updateProgressStats() {
    const userAnswers = userAnswersMap[currentCatKey];
    const flaggedQuestions = flaggedQuestionsMap[currentCatKey];
    const quizList = allQuizData[currentCatKey].questions;

    const answeredCount = userAnswers.filter(answerHasValue).length;
    const flaggedCount = flaggedQuestions.filter(f => f).length;

    document.getElementById('stat-progress').innerText = `${answeredCount} / ${quizList.length}`;
    const pct = quizList.length ? Math.round((answeredCount / quizList.length) * 100) : 0;
    const pctText = document.getElementById('exam-progress-percent'); if (pctText) pctText.textContent = `${pct}%`;
    const pctBar = document.getElementById('exam-progress-bar'); if (pctBar) pctBar.style.width = `${pct}%`;
    document.getElementById('stat-flagged').innerText = `${flaggedCount} 題`;

    const statusText = document.getElementById('bottom-status-text');
    if (isSubmittedMap[currentCatKey]) {
        statusText.innerHTML = `<span class="text-indigo-600 font-bold">🔒 本分頁考核已完成鎖定。</span> 若需重新填答請點擊上方「🔄 重測當前考卷」。`;
    } else if (answeredCount === quizList.length) {
        statusText.innerHTML = `<span class="text-green-600 font-bold">✓ 本分頁所有題目已答完！</span> 請點擊右側按鈕提交試卷。`;
    } else {
        statusText.innerText = `目前已完成 ${answeredCount} / ${quizList.length} 題，剩餘 ${quizList.length - answeredCount} 題未作答。`;
    }
}

function updateAnswerStatus(index){
    const el=document.getElementById(`answer-status-${index}`); if(!el) return;
    const value=userAnswersMap[currentCatKey]?.[index]; const answered=answerHasValue(value);
    el.className=`answer-status-pill ${answered?'answered':'unanswered'}`;
    el.textContent=answered?'✓ 已作答':'○ 未作答';
}

function scrollToFirstUnanswered(){
    const answers=userAnswersMap[currentCatKey]||[]; const idx=answers.findIndex(v=>!answerHasValue(v));
    if(idx<0) return alert('目前所有題目都已作答。'); scrollToQuestion(idx);
}
function scrollToFirstFlagged(){
    const flags=flaggedQuestionsMap[currentCatKey]||[]; const idx=flags.findIndex(Boolean);
    if(idx<0) return alert('目前沒有標記題目。'); scrollToQuestion(idx);
}

function scrollToQuestion(index) {
    const element = document.getElementById(`question-card-${index}`);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function scrollToReview() {
    scrollToQuestion(0);
}

// --- Submit Quiz; server owns answer-key evaluation and score persistence. ---
async function submitQuiz() {
    if (isSubmittedMap[currentCatKey]) {
        alert('本分頁考卷已經提交過，無法重複更改答案！若需重測請點擊「重測當前考卷」。');
        return;
    }

    const nameInput = document.getElementById('examinee-name').value.trim();
    const idInput = document.getElementById('examinee-id').value.trim();
    if (!nameInput || !idInput) {
        alert('請先回首頁設定個人姓名與工號；內頁會自動連動。');
        if (!nameInput || !idInput) { location.hash=''; }
        return;
    }

    const userAnswers = userAnswersMap[currentCatKey] || [];

    const unanswered = userAnswers.filter(a => !answerHasValue(a)).length;
    if (unanswered > 0) {
        const confirmSubmit = confirm(`尚有 ${unanswered} 題未作答，確定要直接提交本份試卷嗎？`);
        if (!confirmSubmit) return;
    }

    const attemptId=secureAttemptMap[currentCatKey]||loadExamDraft(currentCatKey)?.attemptId;
    if(!attemptId){alert('找不到本次考核作答識別碼，請重新整理後再試。');return;}
    const submitBtn=document.getElementById('submit-btn');
    if(submitBtn){submitBtn.disabled=true;submitBtn.textContent='⏳ 伺服器計分中…';}
    let result;
    try {
        result=await secureExamApi(`/api/exam-attempts/${encodeURIComponent(attemptId)}/submit`,{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({answers:userAnswers,responseTimings:questionTimingSeconds(currentCatKey)})
        });
    } catch (error) {
        console.error(error);
        alert(`成績提交失敗：${error.message}\n\n本次考卷尚未鎖定，請確認網路或伺服器後再提交。`);
        if(submitBtn){submitBtn.disabled=false;submitBtn.textContent='📋 提交試卷結算成績';}
        return;
    }

    const reviewed=renumberQuestions((result.questions||[]).map(normalizePublicQuestion));
    if(reviewed.length===allQuizData[currentCatKey].questions.length)allQuizData[currentCatKey].questions=reviewed;
    isSubmittedMap[currentCatKey] = true;
    clearExamDraft(currentCatKey);
    renderQuestions();

    const totalScore=Number(result.score||0),correctCount=Number(result.correctCount||0),wrongCount=Number(result.wrongCount||0),passingScore=Number(result.passingScore||allQuizData[currentCatKey].passingScore||80),essayCount=Number(result.essayCount||0);

    document.getElementById('result-user-info').innerText = `考核者：${nameInput} (工號：${idInput})`;
    document.getElementById('final-score-text').innerText = totalScore;
    document.getElementById('res-correct-count').innerText = `${correctCount} 題`;
    document.getElementById('res-wrong-count').innerText = `${wrongCount} 題`;
    const passEl=document.getElementById('result-passing-score');if(passEl)passEl.textContent=`${passingScore} 分`;

    const badge = document.getElementById('result-badge');
    const comment = document.getElementById('result-summary-comment');

    if (essayCount > 0) {
        badge.className = 'inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-amber-100 text-amber-800';
        badge.innerText = '考核結果：待人工批改';
        comment.innerText = '本卷含問答題，選擇題已由伺服器先行計分；待管理者完成線上批改後，系統會重新計算最終總分與合格結果。';
    } else if (totalScore >= passingScore) {
        badge.className = 'inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-green-100 text-green-800';
        badge.innerText = '考核結果：合格 (PASS)';
        comment.innerText = '恭喜您通過本分頁教育訓練考核！成績已由伺服器計算並儲存至後台系統。';
    } else {
        badge.className = 'inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-red-100 text-red-800';
        badge.innerText = '考核結果：未達及格線 (NEEDS REVIEW)';
        comment.innerText = '建議您返回「教材區」複習相關教材，並檢視下方答錯題目之解析。';
    }

    const resultDashboard = document.getElementById('result-dashboard');
    resultDashboard.classList.remove('hidden');
    resultDashboard.scrollIntoView({ behavior: 'smooth' });

    renderCategoryChart(result.categoryStats||{});
    updateProgressStats();
}
