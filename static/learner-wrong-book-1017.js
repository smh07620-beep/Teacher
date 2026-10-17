/* Learner 錯題本 (2026-10-17). Owner of #wrong-book in the 個人訓練進度 panel.
 * Loads only when the learner presses the button (no background traffic).
 * Answers stay private: the list shows the question, what the learner chose and
 * a jump to the material page the teacher linked (#read/<id>/<page>). */
(function () {
  'use strict';

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const letters = 'ABCDEFGHIJ';

  function optionText(option) {
    return typeof option === 'object' && option ? (option.text || option.label || '') : String(option ?? '');
  }

  function reviewLink(source) {
    if (!source || !source.materialId) return '';
    const page = Number(source.page || 0);
    const label = page ? `回看教材第 ${page} 頁` : '回看教材';
    const title = source.materialTitle ? `（${esc(source.materialTitle)}）` : '';
    return `<a class="btn btn-secondary mt-2" href="#read/${encodeURIComponent(source.materialId)}/${Math.max(1, page)}">${label}</a><span class="text-sm text-slate-500 ml-2">${title}</span>`;
  }

  function item(entry, index) {
    const options = (entry.options || []).map((o, i) => `<li>${letters[i] || i + 1}. ${esc(optionText(o))}</li>`).join('');
    return `<li class="rounded-xl border border-slate-200 bg-white p-3">
      <p class="text-sm text-slate-500">${index + 1}.　${esc(entry.quizTitle)}</p>
      <p class="font-bold text-slate-900 mt-1">${esc(entry.question)}</p>
      ${options ? `<ul class="mt-2 space-y-1 text-sm text-slate-700">${options}</ul>` : ''}
      <p class="note-danger"><b>你上次的答案</b>　${esc(entry.yourAnswer)}</p>
      ${reviewLink(entry.reviewSource)}
    </li>`;
  }

  async function load() {
    const status = document.getElementById('wrong-book-status');
    const list = document.getElementById('wrong-book-list');
    const button = document.getElementById('wrong-book-load');
    if (!status || !list) return;
    status.textContent = '讀取中…';
    if (button) button.disabled = true;
    try {
      const response = await fetch('/api/my/wrong-questions', {credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '錯題本讀取失敗');
      const items = Array.isArray(data.items) ? data.items : [];
      status.textContent = items.length ? `目前有 ${items.length} 題待加強。` : '目前沒有錯題，繼續保持！';
      list.innerHTML = items.map(item).join('');
      if (button) button.textContent = '重新整理';
    } catch (error) {
      status.textContent = `${error.message}，請稍後再試。`;
    } finally {
      if (button) button.disabled = false;
    }
  }

  document.getElementById('wrong-book-load')?.addEventListener('click', load);
  window.LearnerWrongBook = Object.freeze({load});
})();
