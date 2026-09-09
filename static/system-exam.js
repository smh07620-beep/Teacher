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
let chartInstance = null;

// ==================================================================
// 六組考卷皆使用動態考題頁籤 / 題目 —— 全部由後台管理者建立與維護，
// 前端只負責讀取 /api/quiz-categories 與 /api/quiz-questions 並渲染。
// ==================================================================
let dynamicCategoriesCache = {}; // { 'area:group': [ {id,title,desc,...}, ... ] }
let blindTestMode = false;

// V5.4.0：考卷摘要與本機續答快照。
function examBankCount(c){ return Math.max(0, Number(c?.questionCount || 0)); }
function examQuotaTotal(c){const r=c?.drawRules||{},q=r?.quotas||{};return r?.mode==='type_quota'?['choice','multi','true_false','fill','essay','image','video'].reduce((s,k)=>s+Math.max(0,Number(q[k]||0)),0):0;}
function examActualCount(c){ const bank=examBankCount(c), quota=examQuotaTotal(c), draw=Math.max(0,Number(c?.drawCount||0)); return quota>0?Math.min(quota,bank):(draw>0?Math.min(draw,bank):bank); }
function examDrawLabel(c){ const quota=examQuotaTotal(c),draw=Math.max(0,Number(c?.drawCount||0)), bank=examBankCount(c); return quota>0?`依題型配額 ${Math.min(quota,bank||quota)} 題`:(draw>0?`隨機抽 ${Math.min(draw,bank||draw)} 題`:'全部啟用題目'); }
function examAudienceLabel(c){ return String(c?.audience||'所有符合課程資格人員').trim() || '所有符合課程資格人員'; }
function examDraftKey(catId){ return `v540-exam-draft:${currentTrainingArea}:${currentGroupKey}:${catId}`; }
function loadExamDraft(catId){try{const raw=localStorage.getItem(examDraftKey(catId));if(!raw)return null;const d=JSON.parse(raw);return d&&Array.isArray(d.questions)&&Array.isArray(d.answers)?d:null;}catch(_e){return null;}}
function saveExamDraft(catId=currentCatKey){if(!catId||isSubmittedMap[catId]||!allQuizData[catId])return;try{localStorage.setItem(examDraftKey(catId),JSON.stringify({version:1,savedAt:new Date().toISOString(),questions:allQuizData[catId].questions,answers:userAnswersMap[catId]||[],flags:flaggedQuestionsMap[catId]||[]}));}catch(_e){}}
function clearExamDraft(catId=currentCatKey){try{if(catId)localStorage.removeItem(examDraftKey(catId));}catch(_e){}}
function hasExamDraft(catId){
    const d=loadExamDraft(catId);
    if(!d || !Array.isArray(d.answers)) return false;
    return d.answers.some(a => Array.isArray(a) ? a.length>0 : (a!==null && a!==undefined && String(a).trim()!==''));
}

async function renderDynamicExamTabs() {
    const listBox=document.getElementById('dynamic-exam-tabs-list'),emptyBox=document.getElementById('dynamic-exam-tabs-empty');
    listBox.innerHTML='<p class="text-xs text-slate-400">載入課程考卷中…</p>';emptyBox.classList.add('hidden');
    try{
        const [res,courseRes]=await Promise.all([fetch(`/api/quiz-categories?group=${currentGroupKey}&area=${currentTrainingArea}`),fetch(`/api/courses?area=${encodeURIComponent(currentTrainingArea)}&group=${encodeURIComponent(currentGroupKey)}`)]);
        const cats=await res.json();if(courseRes.ok)cachedCourses=await courseRes.json();cachedQuizCategories=Array.isArray(cats)?cats:[];dynamicCategoriesCache[`${currentTrainingArea}:${currentGroupKey}`]=cachedQuizCategories;
        if(!cachedQuizCategories.length){listBox.innerHTML='';emptyBox.classList.remove('hidden');document.getElementById('current-quiz-title').innerHTML=`<span class="text-teal-600">📝</span> ${GROUPS[currentGroupKey].label} 尚無考題`;document.getElementById('current-quiz-desc').innerText='本組別尚未建立任何考卷，請由管理者後台新增。';document.getElementById('quiz-questions-list').innerHTML='';document.getElementById('quick-jump-grid').innerHTML='';document.getElementById('stat-progress').innerText='0 / 0';document.getElementById('stat-flagged').innerText='0 題';document.getElementById('result-dashboard').classList.add('hidden');return;}
        const courseMap=Object.fromEntries((cachedCourses||[]).map(c=>[c.id,c])),courseOrder=(cachedCourses||[]).map(c=>c.id),grouped={};
        cachedQuizCategories.forEach(c=>{const key=c.courseId&&courseMap[c.courseId]?c.courseId:'__orphan__';(grouped[key]||(grouped[key]=[])).push(c);});
        const keys=[...courseOrder.filter(k=>grouped[k]?.length),...(grouped.__orphan__?['__orphan__']:[])];
        listBox.innerHTML=keys.map(k=>{const course=k==='__orphan__'?null:courseMap[k],items=grouped[k]||[];const desc=course?.desc&&course.desc.trim()!==course.title?.trim()?`<div class="text-[11px] text-slate-500 mt-1">${escapeHtml(course.desc)}</div>`:'';return `<section class="rounded-2xl border border-slate-200 bg-slate-50/60 p-3 sm:p-4"><div class="flex items-start justify-between gap-3 mb-3"><div><div class="text-sm font-black text-slate-800">${course?`📘 ${escapeHtml(course.title)}`:'📁 通用考卷'}</div>${desc}</div><span class="text-[11px] font-bold text-slate-500 bg-white border border-slate-200 rounded-full px-2.5 py-1">考卷 ${items.length} 份</span></div><div class="grid md:grid-cols-2 xl:grid-cols-3 gap-2.5">${items.map(c=>{const bank=examBankCount(c),actual=examActualCount(c),draft=hasExamDraft(c.id);return `<button type="button" onclick="switchDynamicCategory('${c.id}')" id="dyn-tab-${c.id}" class="tab-btn text-left rounded-xl border border-slate-200 bg-white hover:border-teal-300 hover:shadow-sm p-3 transition-all"><div class="flex items-start justify-between gap-2"><span class="font-black text-sm text-slate-900">📝 ${escapeHtml(c.title)}</span>${draft?'<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">可續答</span>':''}</div><div class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-500"><span>👤 ${escapeHtml(examAudienceLabel(c))}</span><span>🎯 及格 ${Number(c.passingScore||80)} 分</span><span>🧠 題庫 ${bank} 題</span><span>📋 本次 ${actual} 題</span></div><div class="mt-2 text-[11px] font-bold text-teal-700">${escapeHtml(examDrawLabel(c))} → ${draft?'繼續作答':'開始考核'}</div></button>`;}).join('')}</div></section>`;}).join('');
        const requestedExamId=new URLSearchParams(window.location.search).get('examId')||'';
        const requestedCategory=cachedQuizCategories.find(
            c=>String(c.id)===String(requestedExamId)
        );

        const initialCategory=
            requestedCategory
            || cachedQuizCategories[0];

        await switchDynamicCategory(
            initialCategory.id
        );

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
    if(allQuizData[catId])return;const cats=dynamicCategoriesCache[`${currentTrainingArea}:${currentGroupKey}`]||[],catMeta=cats.find(c=>c.id===catId)||{},draft=loadExamDraft(catId);let normalized=[];
    if(draft?.questions?.length)normalized=draft.questions;else{const res=await fetch(`/api/quiz-questions/random?category=${encodeURIComponent(catId)}`),questions=await res.json();normalized=renumberQuestions((Array.isArray(questions)?questions:[]).map(q=>({id:q.id,category:q.tag||'一般',question:q.question,questionType:q.questionType||'choice',imageUrl:q.imageUrl||'',options:q.options||[],correct:q.correct,explanation:q.explanation,answerConfig:q.answerConfig||{}})));}
    const passingScore=Math.max(1,Math.min(100,Number(catMeta.passingScore||80))),audience=examAudienceLabel(catMeta),baseDesc=(catMeta.desc||'').trim();
    allQuizData[catId]={title:catMeta.title||'考卷',desc:`${baseDesc?baseDesc+' · ':''}適用：${audience} · 本次 ${normalized.length} 題 · 及格 ${passingScore} 分`,courseId:catMeta.courseId||'',blindMode:!!catMeta.blindMode,passingScore,drawCount:Math.max(0,Number(catMeta.drawCount||0)),drawRules:catMeta.drawRules||{},audience,questions:normalized};
    userAnswersMap[catId]=draft?.answers?.length===normalized.length?draft.answers:new Array(normalized.length).fill(null);flaggedQuestionsMap[catId]=draft?.flags?.length===normalized.length?draft.flags:new Array(normalized.length).fill(false);isSubmittedMap[catId]=false;if(!draft)saveExamDraft(catId);
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

    if (isSubmittedMap[currentCatKey]) {
        document.getElementById('result-dashboard').classList.remove('hidden');
    } else {
        document.getElementById('result-dashboard').classList.add('hidden');
    }

    renderQuickJumpGrid();
    renderQuestions();
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
    if(q.imageUrl)return `<div class="question-media"><button type="button" onclick="openQuestionImage('${escapeHtml(q.imageUrl)}','${escapeHtml(q.question)}')" class="w-full"><img src="${escapeHtml(q.imageUrl)}" alt="題目影像" loading="lazy" decoding="async"><span class="block text-[11px] text-white/70 bg-black/50 py-1">🔍 點擊放大影像，支援局部縮放</span></button></div>`;
    const u=q.answerConfig?.mediaUrl||'';const sec=Number(q.answerConfig?.pauseAt||0);
    if(u)return `<div class="question-media"><video id="question-video-${i}" src="${escapeHtml(u)}" controls playsinline preload="metadata" ${(!submitted&&sec>0)?`ontimeupdate="handleVideoQuestionTime(${i},this,${sec})"`:''}></video>${sec>0?`<div id="video-cue-${i}" class="px-3 py-2 bg-slate-900 text-white/80 text-xs">⏱️ 互動影片題：播放至 ${formatSeconds(sec)} 時會自動暫停並開放作答。</div>`:''}</div>`;
    return '';
}
function formatSeconds(sec){sec=Math.max(0,Math.round(Number(sec)||0));return `${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`;}
function handleVideoQuestionTime(i,video,pauseAt){if(!video||video.dataset.questionUnlocked==='1')return;if(video.currentTime+0.15>=Number(pauseAt||0)){video.dataset.questionUnlocked='1';video.pause();const answer=document.getElementById(`video-answer-${i}`);answer?.classList.remove('hidden');const cue=document.getElementById(`video-cue-${i}`);if(cue){cue.textContent='✅ 已到達指定學習節點，請完成下方題目後再繼續播放。';cue.className='px-3 py-2 bg-teal-900 text-teal-50 text-xs font-bold';}answer?.scrollIntoView({behavior:'smooth',block:'nearest'});}}
function renderQuestions(){const c=document.getElementById('quiz-questions-list');c.innerHTML='';const quizList=allQuizData[currentCatKey].questions,userAnswers=userAnswersMap[currentCatKey],flags=flaggedQuestionsMap[currentCatKey],submitted=isSubmittedMap[currentCatKey];quizList.forEach((q,i)=>{const type=q.questionType||'choice',ans=userAnswers[i];let ok=null;if(type==='essay')ok=null;else if(type==='multi'){const a=[...(q.answerConfig?.correctIndices||[])].map(Number).sort(),b=Array.isArray(ans)?[...ans].map(Number).sort():[];ok=JSON.stringify(a)===JSON.stringify(b);}else if(type==='fill'){const cs=!!q.answerConfig?.caseSensitive,n=x=>cs?String(x||'').trim():String(x||'').trim().toLowerCase();ok=(q.answerConfig?.acceptedAnswers||[]).some(x=>n(x)===n(ans));}else ok=ans===q.correct;const card=document.createElement('div');card.id=`question-card-${i}`;card.className=submitted?(type==='essay'?'bg-amber-50/30 p-5 sm:p-6 rounded-2xl border-2 border-amber-300 shadow-sm space-y-4 scroll-mt-24':(ok?'bg-green-50/30 p-5 sm:p-6 rounded-2xl border-2 border-green-400 shadow-sm space-y-4 scroll-mt-24':'bg-red-50/30 p-5 sm:p-6 rounded-2xl border-2 border-red-300 shadow-sm space-y-4 scroll-mt-24')):'question-card-learning micro-card bg-white p-5 sm:p-6 border space-y-4 scroll-mt-28';let body='';if(type==='essay'){body=`<textarea ${submitted?'disabled':''} oninput="selectEssay(${i},this.value)" rows="7" class="w-full min-h-[190px] border border-slate-300 rounded-2xl p-4 text-sm leading-7" placeholder="請在此完整填寫作答內容……">${escapeHtml(typeof ans==='string'?ans:'')}</textarea><p class="text-xs text-slate-400">問答題由考核者人工閱卷。</p>`;}else if(type==='fill'){body=`<input ${submitted?'disabled':''} value="${escapeHtml(typeof ans==='string'?ans:'')}" oninput="selectFill(${i},this.value)" class="fill-answer" placeholder="請輸入答案"><p class="text-xs text-slate-400">請依題意填入關鍵字或數值。</p>`;}else{const set=new Set((q.answerConfig?.correctIndices||[]).map(Number));(q.options||[]).forEach((opt,j)=>{const chosen=type==='multi'?(Array.isArray(ans)&&ans.includes(j)):ans===j;let cls='hover:bg-slate-50 cursor-pointer';if(submitted){const corr=type==='multi'?set.has(j):j===q.correct;if(corr)cls='border-2 border-green-500 bg-green-100/60 font-bold';else if(chosen)cls='border-2 border-red-400 bg-red-100/60';else cls='opacity-60 bg-slate-50';}body+=`<label class="choice-learning flex items-start gap-3 p-4 border ${cls}"><input type="${type==='multi'?'checkbox':'radio'}" ${type==='multi'?'class="multi-check mt-1"':'class="mt-1"'} name="question-${i}" ${chosen?'checked':''} ${submitted?'disabled':''} onchange="${type==='multi'?`selectMulti(${i},${j},this.checked)`:`selectOption(${i},${j})`}"><span class="text-sm font-medium"><b class="mr-1">${String.fromCharCode(65+j)}.</b>${escapeHtml(opt)}</span></label>`;});}const expl=submitted&&q.explanation?`<div class="p-4 rounded-xl bg-slate-50 border border-slate-200"><div class="font-bold text-teal-800">💡 教學解析</div><div class="text-xs sm:text-sm text-slate-600 mt-1">${escapeHtml(q.explanation)}</div></div>`:'';const videoLocked=!!q.answerConfig?.mediaUrl&&Number(q.answerConfig?.pauseAt||0)>0&&!submitted&&!answerHasValue(ans);card.innerHTML=`<div class="flex flex-wrap justify-between gap-2 border-b border-slate-100 pb-3"><div class="flex items-center gap-2 flex-wrap"><span class="w-8 h-8 rounded-lg bg-[#0b3342] text-white flex items-center justify-center font-black">${i+1}</span>${blindTestMode?'':`<span class="text-xs font-bold px-2.5 py-1 rounded-full bg-teal-100 text-teal-800">${escapeHtml(q.category||q.tag||'一般')}</span>`}<span class="question-type-pill ${type==='multi'?'bg-violet-100 text-violet-800':type==='fill'?'bg-sky-100 text-sky-800':type==='essay'?'bg-amber-100 text-amber-800':'bg-slate-100 text-slate-600'}">${q.answerConfig?.mediaUrl?'影片・':''}${questionTypeLabel(type)}</span><span id="answer-status-${i}" class="answer-status-pill ${answerHasValue(ans)?'answered':'unanswered'}">${answerHasValue(ans)?'✓ 已作答':'○ 未作答'}</span></div><button onclick="toggleFlag(${i})" id="flag-btn-${i}" class="text-xs px-2.5 py-1 rounded-lg border border-slate-200">${flags[i]?'🚩 取消標記':'🏳️ 標記此題'}</button></div>${renderQuestionMedia(q,i,submitted)}<div id="video-answer-${i}" class="${videoLocked?'hidden ':''}space-y-4"><h3 class="text-base sm:text-lg font-black leading-relaxed">${escapeHtml(q.question)}</h3><div class="space-y-2.5">${body}</div></div>${expl}`;c.appendChild(card);});const b=document.getElementById('submit-btn');if(submitted){b.disabled=true;b.className='w-full sm:w-auto bg-slate-400 text-white font-bold px-8 py-3 rounded-xl shadow cursor-not-allowed';b.textContent='🔒 本分頁考卷已繳交';}else{b.disabled=false;b.className='w-full sm:w-auto bg-amber-600 hover:bg-amber-500 text-white font-bold px-8 py-3 rounded-xl shadow-lg';b.textContent='📋 提交試卷結算成績';}updateQuickJumpButtons();}
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

// --- Submit Quiz & Calculate Final Results ---
async function submitQuiz() {
    if (isSubmittedMap[currentCatKey]) {
        alert('本分頁考卷已經提交過，無法重複更改答案！若需重測請點擊「重測當前考卷」。');
        return;
    }

    const nameInput = document.getElementById('examinee-name').value.trim();
    const idInput = document.getElementById('examinee-id').value.trim();
    const roleInput = document.getElementById('examinee-role').value;
    const evaluatorNameInput = document.getElementById('evaluator-name').value.trim();
    const evaluatorTitleInput = document.getElementById('evaluator-title').value;

    if (!nameInput || !idInput || !roleInput || !evaluatorNameInput || !evaluatorTitleInput) {
        alert(!nameInput||!idInput?'請先回首頁設定個人姓名與工號；內頁會自動連動。':'請填寫考試人員類別、考核人員姓名與考核人員職稱後再提交考卷。');
        if (!nameInput || !idInput) { location.hash=''; }
        else if (!roleInput) document.getElementById('examinee-role').focus();
        else if (!evaluatorNameInput) document.getElementById('evaluator-name').focus();
        else document.getElementById('evaluator-title').focus();
        return;
    }
    rememberEvaluatorFields();

    const quizList = allQuizData[currentCatKey].questions;
    const userAnswers = userAnswersMap[currentCatKey];
    const passingScore = Math.max(1, Math.min(100, Number(allQuizData[currentCatKey].passingScore || 80)));

    const unanswered = userAnswers.filter(a => !answerHasValue(a)).length;
    if (unanswered > 0) {
        const confirmSubmit = confirm(`尚有 ${unanswered} 題未作答，確定要直接提交本份試卷嗎？`);
        if (!confirmSubmit) return;
    }

    let correctCount = 0;
    let wrongCount = 0;
    const categoryStats = {};
    const userAnswersDetail = [];

    quizList.forEach((q, qIndex) => {
        const userChoice=userAnswers[qIndex]; const type=q.questionType||'choice'; const isEssay=type==='essay'; let isCorrect=null;
        if(!isEssay){if(type==='multi'){const a=[...(q.answerConfig?.correctIndices||[])].map(Number).sort(),b=Array.isArray(userChoice)?[...userChoice].map(Number).sort():[];isCorrect=JSON.stringify(a)===JSON.stringify(b);}else if(type==='fill'){const cs=!!q.answerConfig?.caseSensitive,n=x=>cs?String(x||'').trim():String(x||'').trim().toLowerCase();isCorrect=(q.answerConfig?.acceptedAnswers||[]).some(x=>n(x)===n(userChoice));}else isCorrect=userChoice===q.correct;}
        const optionLetters=['A','B','C','D','E','F']; let selectedLetter='未答'; if(type==='essay'||type==='fill')selectedLetter=userChoice||'未答';else if(type==='multi')selectedLetter=Array.isArray(userChoice)&&userChoice.length?userChoice.map(i=>optionLetters[i]).join('、'):'未答';else if(userChoice!==null&&userChoice!=='')selectedLetter=type==='true_false'?((q.options||[])[userChoice]||'未答'):optionLetters[userChoice];
        userAnswersDetail.push({num:qIndex+1,questionText:q.question,questionType:type,userAnswer:selectedLetter,isCorrect});
        if (isEssay) return;

        if (!categoryStats[q.category]) {
            categoryStats[q.category] = { total: 0, correct: 0 };
        }
        categoryStats[q.category].total += 1;

        if (isCorrect) {
            correctCount++;
            categoryStats[q.category].correct += 1;
        } else {
            wrongCount++;
        }
    });

    const essayCount = quizList.filter(q => (q.questionType || "choice") === "essay").length;
    const totalScore = quizList.length > 0 ? Math.round((correctCount / quizList.length) * 100) : 0;

    const record = {
        id: Date.now(),
        timestamp: new Date().toLocaleString(),
        name: nameInput,
        empId: idInput,
        role: roleInput,
        evaluatorName: evaluatorNameInput,
        evaluatorTitle: evaluatorTitleInput,
        quizTitle: allQuizData[currentCatKey].title,
        groupKey: currentGroupKey,
        trainingArea: currentTrainingArea,
        courseId: allQuizData[currentCatKey].courseId || '',
        quizCategoryId: currentCatKey,
        passingScore,
        score: totalScore,
        status: essayCount > 0 ? '待人工批改' : (totalScore >= passingScore ? '合格' : '未達標'),
        correctCount, wrongCount,
        answersDetail: userAnswersDetail
    };
    try {
        await saveRecordToServer(record);
    } catch (error) {
        console.error(error);
        alert(`成績儲存失敗：${error.message}\n\n本次考卷尚未鎖定，請確認網路或伺服器後再提交。`);
        return;
    }

    isSubmittedMap[currentCatKey] = true;
    clearExamDraft(currentCatKey);
    renderQuestions();

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
        comment.innerText = '本卷含問答題，選擇題已先自動計分；待管理者完成線上批改後，系統會重新計算最終總分與合格結果。';
    } else if (totalScore >= passingScore) {
        badge.className = 'inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-green-100 text-green-800';
        badge.innerText = '考核結果：合格 (PASS)';
        comment.innerText = '恭喜您通過本分頁生化教育訓練考核！成績與題目細項已自動儲存至後台系統。';
    } else {
        badge.className = 'inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-red-100 text-red-800';
        badge.innerText = '考核結果：未達及格線 (NEEDS REVIEW)';
        comment.innerText = '建議您返回「教材區」複習相關教材，並檢視下方答錯題目之解析。';
    }

    const resultDashboard = document.getElementById('result-dashboard');
    resultDashboard.classList.remove('hidden');
    resultDashboard.scrollIntoView({ behavior: 'smooth' });

    renderCategoryChart(categoryStats);
    updateProgressStats();
}

async function saveRecordToServer(record) {
    const res = await fetch('/api/records', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || '成績儲存失敗');
    return data;
}
