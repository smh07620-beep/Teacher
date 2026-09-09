/* Teacher 6.3 · server-authoritative exam attempts */
(function(){
'use strict';
const secureAttemptMap={};
function secureDraftKey(catId){return `v630-secure-exam:${currentTrainingArea}:${currentGroupKey}:${catId}`;}
function readSecureDraft(catId){try{const raw=localStorage.getItem(secureDraftKey(catId));if(!raw)return null;const d=JSON.parse(raw);return d&&d.version===2&&d.attemptId&&Array.isArray(d.answers)?d:null;}catch(_){return null;}}
function writeSecureDraft(catId=currentCatKey){if(!catId||isSubmittedMap[catId]||!allQuizData[catId]||!secureAttemptMap[catId])return;try{localStorage.setItem(secureDraftKey(catId),JSON.stringify({version:2,attemptId:secureAttemptMap[catId],savedAt:new Date().toISOString(),answers:userAnswersMap[catId]||[],flags:flaggedQuestionsMap[catId]||[]}));}catch(_){}}
function removeSecureDraft(catId=currentCatKey){try{if(catId){localStorage.removeItem(secureDraftKey(catId));localStorage.removeItem(examDraftKey(catId));}}catch(_){}}
function purgeLegacyDraft(catId){try{const raw=localStorage.getItem(examDraftKey(catId));if(raw){const d=JSON.parse(raw);if(!d||d.version!==2)localStorage.removeItem(examDraftKey(catId));}}catch(_){try{localStorage.removeItem(examDraftKey(catId));}catch(__){}}}

loadExamDraft=function(catId){purgeLegacyDraft(catId);return readSecureDraft(catId);};
saveExamDraft=function(catId=currentCatKey){writeSecureDraft(catId);};
clearExamDraft=function(catId=currentCatKey){removeSecureDraft(catId);};
hasExamDraft=function(catId){const d=readSecureDraft(catId);return !!(d&&d.answers.some(a=>Array.isArray(a)?a.length>0:(a!==null&&a!==undefined&&String(a).trim()!=='')));};

function normalizePublicQuestion(q){return {id:q.id,questionId:q.id,category:q.tag||q.category||'一般',tag:q.tag||q.category||'一般',question:q.question,questionType:q.questionType||'choice',imageUrl:q.imageUrl||'',options:q.options||[],explanation:q.explanation||'',answerConfig:q.answerConfig||{},correct:q.correct};}
async function secureApi(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options});const d=await r.json().catch(()=>({}));if(!r.ok){const e=new Error(d.error||`HTTP ${r.status}`);e.status=r.status;e.data=d;throw e;}return d;}

ensureDynamicCategoryLoaded=async function(catId){
    if(allQuizData[catId])return;
    const cats=dynamicCategoriesCache[`${currentTrainingArea}:${currentGroupKey}`]||[],catMeta=cats.find(c=>c.id===catId)||{};
    let draft=readSecureDraft(catId),attempt=null;
    if(draft?.attemptId){
        try{attempt=await secureApi(`/api/exam-attempts/${encodeURIComponent(draft.attemptId)}`);}catch(e){if([404,409,410].includes(e.status)){removeSecureDraft(catId);draft=null;}else throw e;}
    }
    if(!attempt){attempt=await secureApi('/api/exam-attempts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quizCategoryId:catId})});draft=null;}
    secureAttemptMap[catId]=attempt.attemptId;
    const normalized=renumberQuestions((attempt.questions||[]).map(normalizePublicQuestion));
    const passingScore=Math.max(1,Math.min(100,Number(attempt.passingScore||catMeta.passingScore||80))),audience=examAudienceLabel(catMeta),baseDesc=(catMeta.desc||'').trim();
    allQuizData[catId]={title:attempt.quizTitle||catMeta.title||'考卷',desc:`${baseDesc?baseDesc+' · ':''}適用：${audience} · 本次 ${normalized.length} 題 · 及格 ${passingScore} 分`,courseId:attempt.courseId||catMeta.courseId||'',blindMode:!!catMeta.blindMode,passingScore,drawCount:Math.max(0,Number(catMeta.drawCount||0)),drawRules:catMeta.drawRules||{},audience,questions:normalized};
    userAnswersMap[catId]=draft?.answers?.length===normalized.length?draft.answers:new Array(normalized.length).fill(null);
    flaggedQuestionsMap[catId]=draft?.flags?.length===normalized.length?draft.flags:new Array(normalized.length).fill(false);
    isSubmittedMap[catId]=false;writeSecureDraft(catId);
};

submitQuiz=async function(){
    if(isSubmittedMap[currentCatKey]){alert('本分頁考卷已經提交過，無法重複更改答案！若需重測請點擊「重測當前考卷」。');return;}
    const nameInput=document.getElementById('examinee-name').value.trim(),idInput=document.getElementById('examinee-id').value.trim(),roleInput=document.getElementById('examinee-role').value,evaluatorNameInput=document.getElementById('evaluator-name').value.trim(),evaluatorTitleInput=document.getElementById('evaluator-title').value;
    if(!nameInput||!idInput||!roleInput||!evaluatorNameInput||!evaluatorTitleInput){alert(!nameInput||!idInput?'請先回首頁設定個人姓名與工號；內頁會自動連動。':'請填寫考試人員類別、考核人員姓名與考核人員職稱後再提交考卷。');if(!nameInput||!idInput)location.hash='';else if(!roleInput)document.getElementById('examinee-role').focus();else if(!evaluatorNameInput)document.getElementById('evaluator-name').focus();else document.getElementById('evaluator-title').focus();return;}
    rememberEvaluatorFields();
    const userAnswers=userAnswersMap[currentCatKey]||[],unanswered=userAnswers.filter(a=>!answerHasValue(a)).length;
    if(unanswered>0&&!confirm(`尚有 ${unanswered} 題未作答，確定要直接提交本份試卷嗎？`))return;
    const attemptId=secureAttemptMap[currentCatKey]||readSecureDraft(currentCatKey)?.attemptId;
    if(!attemptId){alert('找不到本次考核作答識別碼，請重新整理後再試。');return;}
    const submitBtn=document.getElementById('submit-btn');if(submitBtn){submitBtn.disabled=true;submitBtn.textContent='⏳ 伺服器計分中…';}
    let result;
    try{result=await secureApi(`/api/exam-attempts/${encodeURIComponent(attemptId)}/submit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:userAnswers,evaluatorName:evaluatorNameInput,evaluatorTitle:evaluatorTitleInput,examineeRole:roleInput})});}
    catch(error){console.error(error);alert(`成績提交失敗：${error.message}\n\n本次考卷尚未鎖定，請確認網路或伺服器後再提交。`);if(submitBtn){submitBtn.disabled=false;submitBtn.textContent='📋 提交試卷結算成績';}return;}
    const reviewed=renumberQuestions((result.questions||[]).map(normalizePublicQuestion));if(reviewed.length===allQuizData[currentCatKey].questions.length)allQuizData[currentCatKey].questions=reviewed;
    isSubmittedMap[currentCatKey]=true;removeSecureDraft(currentCatKey);renderQuestions();
    const totalScore=Number(result.score||0),correctCount=Number(result.correctCount||0),wrongCount=Number(result.wrongCount||0),passingScore=Number(result.passingScore||allQuizData[currentCatKey].passingScore||80),essayCount=Number(result.essayCount||0);
    document.getElementById('result-user-info').innerText=`考核者：${nameInput} (工號：${idInput})`;document.getElementById('final-score-text').innerText=totalScore;document.getElementById('res-correct-count').innerText=`${correctCount} 題`;document.getElementById('res-wrong-count').innerText=`${wrongCount} 題`;const passEl=document.getElementById('result-passing-score');if(passEl)passEl.textContent=`${passingScore} 分`;
    const badge=document.getElementById('result-badge'),comment=document.getElementById('result-summary-comment');
    if(essayCount>0){badge.className='inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-amber-100 text-amber-800';badge.innerText='考核結果：待人工批改';comment.innerText='本卷含問答題，選擇題已由伺服器先行計分；待管理者完成線上批改後，系統會重新計算最終總分與合格結果。';}
    else if(totalScore>=passingScore){badge.className='inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-green-100 text-green-800';badge.innerText='考核結果：合格 (PASS)';comment.innerText='恭喜您通過本分頁教育訓練考核！成績已由伺服器計算並儲存至後台系統。';}
    else{badge.className='inline-block px-4 py-1.5 rounded-full text-sm font-bold bg-red-100 text-red-800';badge.innerText='考核結果：未達及格線 (NEEDS REVIEW)';comment.innerText='建議您返回教材區複習相關教材，並檢視下方答錯題目之解析。';}
    const dashboard=document.getElementById('result-dashboard');dashboard.classList.remove('hidden');dashboard.scrollIntoView({behavior:'smooth'});renderCategoryChart(result.categoryStats||{});updateProgressStats();
};

saveRecordToServer=async function(){throw new Error('6.3 起成績只能由伺服器考核流程建立。');};
})();
