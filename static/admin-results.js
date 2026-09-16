/* Phase 3 · Admin results/review module.
 * Loaded after the legacy admin bundle so these functions become the
 * canonical runtime implementation while the old bundle remains a
 * compatibility fallback during the incremental split.
 */
(function(){
  'use strict';

  let currentReviewRecordIndex = null;

  window.openEssayReview = function(index){
    const r = adminRecords[index];
    if(!r) return;
    currentReviewRecordIndex = index;
    const essays = (r.answersDetail || []).map((a,i)=>({a,i})).filter(x=>x.a.questionType === 'essay');
    if(!essays.length){ alert('此考卷沒有問答題。'); return; }
    document.getElementById('essay-review-panel').classList.remove('hidden');
    document.getElementById('essay-review-meta').textContent = `${r.name}｜${r.empId}｜${r.quizTitle}｜目前：${r.reviewStatus==='pending'?'待批改':`${r.score} 分`}`;
    document.getElementById('essay-reviewer-name').value = r.reviewerName || r.evaluatorName || readLocalMemory(EVALUATOR_NAME_MEMORY_KEY) || '';
    document.getElementById('essay-review-comment').value = r.reviewComment || '';
    document.getElementById('essay-review-questions').innerHTML = essays.map(({a,i})=>`<div class="bg-white border border-rose-100 rounded-xl p-3 space-y-2"><div class="font-semibold text-sm text-slate-800">第 ${i+1} 題：${escapeHtml(a.questionText||'')}</div><div class="text-sm bg-slate-50 rounded-lg p-3 whitespace-pre-wrap">${escapeHtml(a.userAnswer||'未答')}</div><div class="grid grid-cols-1 md:grid-cols-4 gap-2 items-center"><label class="text-xs font-bold text-slate-600">本題分數 0–100</label><input id="essay-score-${i}" type="number" min="0" max="100" step="1" value="${a.reviewScore ?? ''}" class="px-2 py-1.5 border rounded-lg text-sm"><input id="essay-comment-${i}" type="text" value="${escapeHtml(a.reviewComment||'')}" placeholder="本題評語（選填）" class="md:col-span-2 px-2 py-1.5 border rounded-lg text-sm"></div>${a.reviewerName?`<div class="text-[11px] text-slate-500">上次批改者：${escapeHtml(a.reviewerName)}${a.reviewedAt?'・'+escapeHtml(a.reviewedAt):''}</div>`:''}</div>`).join('');
    document.getElementById('essay-review-panel').scrollIntoView({behavior:'smooth'});
  };

  window.closeEssayReview = function(){
    document.getElementById('essay-review-panel').classList.add('hidden');
    currentReviewRecordIndex = null;
  };

  window.submitEssayReview = async function(){
    if(currentReviewRecordIndex === null) return;
    const r = adminRecords[currentReviewRecordIndex];
    const key = await getAdminKey();
    if(!key) return;
    const reviewerName = document.getElementById('essay-reviewer-name').value.trim();
    if(!reviewerName){
      alert('請填寫批改者姓名；每一題問答題都會保存此批改者。');
      return;
    }
    const essayScores = {}, essayComments = {};
    const missing = [];
    (r.answersDetail || []).forEach((a,i)=>{
      if(a.questionType !== 'essay') return;
      const value = document.getElementById(`essay-score-${i}`).value;
      if(value === '') missing.push(i + 1);
      essayScores[i] = value;
      essayComments[i] = document.getElementById(`essay-comment-${i}`).value;
    });
    if(missing.length){
      alert(`問答題必須逐題給分。尚未評分：第 ${missing.join('、')} 題`);
      return;
    }
    const res = await fetch(`/api/records/${encodeURIComponent(r.id)}/review`, {
      method:'PATCH',
      headers:{'Content-Type':'application/json','X-Admin-Key':key},
      body:JSON.stringify({
        essayScores,
        essayComments,
        reviewerName,
        reviewComment:document.getElementById('essay-review-comment').value
      })
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok){ alert(data.error || '批改儲存失敗'); return; }
    alert(`批改完成，最終成績 ${data.score} 分（${data.status}）`);
    window.closeEssayReview();
    await renderAdminTable();
  };
})();
