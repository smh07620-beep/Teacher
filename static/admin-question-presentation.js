/* Teacher 7.4 · Quiz workspace presentation helper. */
(function(){
  'use strict';
  window.updateQuizWorkspacePresentation=function(){
    const title=document.querySelector('#admin-quiz-workspace h4');
    const desc=document.querySelector('#admin-quiz-workspace h4 + p');
    if(title) title.textContent='📝 題庫與考卷';
    if(desc) desc.textContent='考卷、題庫、AI 出題、出題藍圖與題目分析集中管理；預設顯示考卷。';
    document.querySelectorAll('[data-admin-role="questions-action"],[data-admin-role="exam-action"]').forEach(node=>node.classList.remove('hidden'));
  };
})();
