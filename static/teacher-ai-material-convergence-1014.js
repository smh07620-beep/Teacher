/* Keep the legacy standalone script studio hidden after AI 教材助手 convergence. */
(function () {
  'use strict';

  function converge() {
    const assistant = document.getElementById('teacher-ai-material-1014');
    const legacy = document.getElementById('teacher-media-script-1014');
    if (!assistant || !legacy) return false;
    const narrationFlow = legacy.closest('#teacher-media-panel-narration-1018');
    if (narrationFlow) {
      legacy.classList.remove('hidden');
      legacy.removeAttribute('aria-hidden');
      return true;
    }
    if (!legacy.classList.contains('hidden')) legacy.classList.add('hidden');
    if (legacy.getAttribute('aria-hidden') !== 'true') legacy.setAttribute('aria-hidden', 'true');
    return true;
  }

  const TARGET_SELECTOR='#teacher-ai-material-1014,#teacher-media-script-1014';
  let observer = null;

  function nodeTouchesTarget(node) {
    if (!(node instanceof Element)) return false;
    return node.matches?.(TARGET_SELECTOR) || Boolean(node.querySelector?.(TARGET_SELECTOR));
  }

  function tryConverge() {
    if (!converge()) return false;
    observer?.disconnect();
    return true;
  }

  if (!tryConverge()) {
    observer = new MutationObserver(records => {
      if (records.some(record => [...(record.addedNodes || [])].some(nodeTouchesTarget))) tryConverge();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }
  [250, 900, 2200].forEach(delay => setTimeout(tryConverge, delay));
})();
