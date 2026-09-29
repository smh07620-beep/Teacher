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
      ? '教材轉講稿、教師核准、免費本機 AI 語音、老師錄音、攝影機錄影與螢幕＋麥克風錄製已接入現有教材流程。AI 語音由本機 Kokoro Worker 產生，不使用 OpenAI TTS。'
      : '教材轉講稿、教師核准、老師錄音、攝影機錄影與螢幕＋麥克風錄製已接入現有教材流程。免費 AI 語音需本機 Kokoro Worker 與 Cloudflare R2 就緒後才會啟用。';
  }

  async function refresh() {
    if (!audioCard()) return false;
    paintBadge('真人錄音可用｜檢查免費 AI 語音…', false);
    try {
      const response = await fetch('/api/media-audio/status', {credentials:'same-origin', cache:'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'status unavailable');
      const enabled = !!data.enabled;
      paintBadge(enabled ? '可使用｜真人錄音＋免費 AI 語音' : '真人錄音可用｜免費 AI 語音待設定', enabled);
      updateSummary(enabled);
    } catch (_) {
      paintBadge('真人錄音可用｜免費 AI 語音狀態待確認', false);
      updateSummary(false);
    }
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

  window.TeacherMediaStatusFix1014 = Object.freeze({ refresh });
})();
