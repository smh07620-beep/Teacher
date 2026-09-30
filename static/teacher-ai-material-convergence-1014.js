/* Keep the legacy standalone script studio hidden after AI 教材助手 convergence. */
(function () {
  'use strict';

  function converge() {
    const assistant = document.getElementById('teacher-ai-material-1014');
    const legacy = document.getElementById('teacher-media-script-1014');
    if (assistant && legacy) {
      legacy.classList.add('hidden');
      legacy.setAttribute('aria-hidden', 'true');
    }
  }

  const observer = new MutationObserver(converge);
  observer.observe(document.body, {childList:true, subtree:true});
  [0, 250, 900, 2200].forEach(delay => setTimeout(converge, delay));
})();
