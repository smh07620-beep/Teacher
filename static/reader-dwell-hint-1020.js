/* Reader 「這頁還要看幾秒」 hint (2026-10-20). Owner of #reader-dwell-hint in the reader footer.
 * The server says how long each page must stay open (dwellRule.requiredByPage, reader rules v2)
 * and how long it already has (position.pageDwell); this file only counts down locally between
 * the 30-second progress saves and lists the pages that still need time. Decks with narration,
 * videos and finished materials show nothing. */
(function () {
  'use strict';

  const state = {materialId: '', page: 0, enteredAt: 0, required: {}, have: {}, applies: false, completed: false};

  const el = () => document.getElementById('reader-dwell-hint');
  const need = page => Number(state.required[String(page)] || 0);
  const had = page => Number(state.have[String(page)] || 0) + (page === state.page && state.enteredAt && !document.hidden ? (Date.now() - state.enteredAt) / 1000 : 0);
  const left = page => Math.max(0, Math.ceil(need(page) - had(page)));

  function paint() {
    const node = el();
    if (!node) return;
    if (!state.applies || state.completed || !state.page) { node.hidden = true; node.textContent = ''; return; }
    const pages = Object.keys(state.required).map(Number).sort((a, b) => a - b);
    const missing = pages.filter(p => left(p) > 0);
    if (!missing.length) { node.hidden = false; node.className = 'reader-dwell-hint is-done'; node.textContent = '✓ 每一頁都看夠了'; return; }
    const here = left(state.page);
    const others = missing.filter(p => p !== state.page);
    const list = others.slice(0, 6).map(p => `<button type="button" data-dwell-page="${p}">第 ${p} 頁</button>`).join('、') + (others.length > 6 ? ` 等 ${others.length} 頁` : '');
    node.hidden = false;
    node.className = 'reader-dwell-hint';
    node.innerHTML = (here > 0 ? `<b>本頁還要 ${here} 秒</b>` : '<b>✓ 本頁已看夠</b>') + (others.length ? `<span>　還沒看夠：${list}</span>` : '');
  }

  window.addEventListener('smartLearning67:progress', event => {
    const data = event.detail || {};
    if (!data.materialId || data.materialId !== state.materialId) return;
    const rule = data.dwellRule || {};
    state.applies = !!rule.applies;
    if (rule.requiredByPage) state.required = rule.requiredByPage;
    state.have = (data.position && data.position.pageDwell) || {};
    state.completed = !!data.completed;
    if (state.page) state.enteredAt = Date.now();  // server dwell now includes the time so far
    paint();
  });

  window.addEventListener('teacher:reader-changed', async event => {
    const {open, materialId, page} = event.detail || {};
    if (!open) { state.page = 0; paint(); return; }
    if (state.page && state.enteredAt && !document.hidden) {
      state.have[String(state.page)] = had(state.page);  // keep the local count when turning pages
    }
    state.page = Number(page) || 0;
    state.enteredAt = Date.now();
    if (materialId !== state.materialId) {
      Object.assign(state, {materialId, required: {}, have: {}, applies: false, completed: false});
      try {
        const response = await fetch(`/api/learning-progress/${encodeURIComponent(materialId)}`, {credentials: 'same-origin', cache: 'no-store'});
        const data = await response.json().catch(() => ({}));
        if (response.ok && materialId === state.materialId) {
          state.applies = !!(data.dwellRule && data.dwellRule.applies);
          state.required = (data.dwellRule && data.dwellRule.requiredByPage) || {};
          state.have = (data.position && data.position.pageDwell) || {};
          state.completed = !!data.completed;
        }
      } catch (_) { /* offline: no hint */ }
    }
    paint();
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden && state.page) { state.have[String(state.page)] = had(state.page); state.enteredAt = 0; }
    else if (state.page) state.enteredAt = Date.now();
  });
  document.addEventListener('click', event => {
    const button = event.target.closest?.('[data-dwell-page]');
    if (button) window.goToSlidePage?.(Number(button.dataset.dwellPage) - 1);
  });
  setInterval(() => { if (state.page && state.applies && !state.completed) paint(); }, 1000);
  window.ReaderDwellHint1020 = Object.freeze({paint});
})();
