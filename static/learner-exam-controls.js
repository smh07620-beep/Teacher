/* Phase 3W · Learner exam/SOP compatibility controls.
 * Kept separate from admin runtime: these globals are invoked by learner HTML
 * and system-learner.js, while their state continues to live in the learner
 * runtime that owns it.
 */
(function(){
  'use strict';

  window.resetCurrentQuiz = function(){
    if(!confirm('確定要重置本分頁試卷並清空已選答案與解鎖填答限制嗎？')) return;
    isSubmittedMap[currentCatKey] = false;
    const qCount = allQuizData[currentCatKey].questions.length;
    userAnswersMap[currentCatKey] = new Array(qCount).fill(null);
    flaggedQuestionsMap[currentCatKey] = new Array(qCount).fill(false);
    clearExamDraft(currentCatKey);
    saveExamDraft(currentCatKey);
    document.getElementById('result-dashboard').classList.add('hidden');
    renderQuestions();
    updateProgressStats();
    window.scrollTo({top:0,behavior:'smooth'});
  };

  window.toggleSopModal = function(show){
    const modal = document.getElementById('sop-modal');
    if(show) modal.classList.remove('hidden');
    else modal.classList.add('hidden');
  };
})();
