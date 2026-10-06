/* Teacher 10/14: media readiness reflects free local Kokoro narration. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  if (typeof R.hasPermission !== 'function' || !R.hasPermission('material.manage')) return;

  function audioCard() {
    return [...document.querySelectorAll('#teacher-media-production-1014 article')]
      .find(card => (card.querySelector('h5')?.textContent || '').includes('老師錄音／AI 語音')) || null;
  }

  function paintBadge(text, enabled) {
    const card = audioCard();
    if (!card) return false;
    const badge = card.querySelector('[data-teacher1014-readiness]') || card.querySelector('span');
    if (!badge) return false;
    badge.textContent = text;
    badge.className = enabled
      ? 'mt-3 inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-800'
      : 'mt-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-800';
    return true;
  }

  function updateSummary(enabled) {
    const summary = document.getElementById('teacher-media-mvp-summary-1014');
    if (!summary) return;
    const paragraph = summary.querySelector('p.mt-1.text-xs');
    if (paragraph) paragraph.textContent = enabled
      ? '教材轉講稿、教師核准、AI 語音、老師錄音、攝影機錄影與螢幕＋麥克風錄製已接入現有教材流程。'
      : '教材轉講稿、教師核准、老師錄音、攝影機錄影與螢幕＋麥克風錄製可正常使用；AI 語音目前暫時不可用。';
  }

  function readinessLabel(data) {
    if (data?.readyForPreview) return '可使用｜真人錄音＋AI 語音';
    if (data?.enabled === false) return '真人錄音可用｜AI 語音尚未啟用';
    return '真人錄音可用｜AI 語音暫時不可用';
  }

  async function refresh() {
    if (!audioCard()) return false;
    const data = window.TeacherMediaAudioStatus1014 || null;
    if (!data) {
      paintBadge('真人錄音可用｜AI 語音狀態確認中…', false);
      updateSummary(false);
      return true;
    }
    const ready = !!data.readyForPreview;
    paintBadge(readinessLabel(data), ready);
    updateSummary(ready);
    return true;
  }

  if (!(await refresh())) {
    const observer = new MutationObserver(() => {
      if (audioCard()) {
        observer.disconnect();
        void refresh();
      }
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.addEventListener('teacher-media-audio-status-1014', event => {
    const data = event.detail?.status || null;
    if (!data || !audioCard()) return;
    const ready = !!data.readyForPreview;
    paintBadge(readinessLabel(data), ready);
    updateSummary(ready);
  });

  window.TeacherMediaStatusFix1014 = Object.freeze({ refresh });
})();
