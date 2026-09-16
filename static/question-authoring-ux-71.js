/* Teacher 7.1: teacher-first question authoring UX overlay.
 *
 * This file does not own question persistence. It keeps the canonical
 * assessment-681 APIs and only improves presentation / safe invocation.
 */
(function () {
  'use strict';

  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  async function api(url, options = {}) {
    const headers = {...(options.headers || {})};
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, {...options, headers, credentials: 'same-origin'});
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.href = `/login?next=${next}`;
      throw new Error('登入已逾時，請重新登入。');
    }
    if (!response.ok) throw new Error(body.error || `操作失敗（${response.status}）`);
    return body;
  }

  function labelFor(id) {
    return document.getElementById(id)?.closest('label') || null;
  }

  function renameLabel(id, text) {
    const label = labelFor(id);
    if (!label) return;
    const control = document.getElementById(id);
    const textNodes = [...label.childNodes].filter(node => node.nodeType === Node.TEXT_NODE);
    textNodes.forEach(node => node.remove());
    let title = label.querySelector(':scope > [data-authoring-label]');
    if (!title) {
      title = document.createElement('span');
      title.dataset.authoringLabel = '1';
      title.className = 'block text-xs font-bold text-slate-600';
      label.insertBefore(title, control);
    }
    title.textContent = text;
  }

  function translateSelect(id, labels) {
    const select = document.getElementById(id);
    if (!select) return;
    [...select.options].forEach(option => {
      if (labels[option.value]) option.textContent = labels[option.value];
    });
  }

  function makeAnswerSelect() {
    const input = document.getElementById('qb681-correct');
    if (!input || input.tagName === 'SELECT') return;
    const current = Number(input.value || 0);
    const select = document.createElement('select');
    select.id = input.id;
    select.className = input.className || 'mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm font-normal';
    ['A', 'B', 'C', 'D'].forEach((letter, index) => {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = `${letter}（選項 ${index + 1}）`;
      if (index === current) option.selected = true;
      select.appendChild(option);
    });
    input.replaceWith(select);
  }

  function statusName(value) {
    return ({draft: '草稿', reviewed: '已審核', published: '已發布', retired: '已停用'})[value] || value || '草稿';
  }

  function originName(value) {
    return ({manual: '手動建立', ai_generated: 'AI 產生', imported: '匯入'})[value] || value || '手動建立';
  }

  function simplifyQuestionDrawer(questionId) {
    const content = document.getElementById('question-bank-drawer-content');
    const question = document.getElementById('qb681-question');
    if (!content || !question) return;
    content.dataset.questionId = questionId || '';

    const header = content.firstElementChild;
    const heading = header?.querySelector('h4');
    if (heading) heading.textContent = questionId ? '✏️ 編輯題目' : '＋ 設計新題目';

    const status = document.getElementById('qb681-status')?.value || 'draft';
    const origin = document.getElementById('qb681-origin')?.value || 'manual';
    if (header && !header.querySelector('[data-question-state]')) {
      const meta = document.createElement('div');
      meta.dataset.questionState = '1';
      meta.className = 'ml-auto mr-2 flex items-center gap-2 text-[11px] text-slate-500';
      meta.innerHTML = `<span class="rounded-full bg-slate-100 px-2 py-1 font-bold">${esc(statusName(status))}</span><span>${esc(originName(origin))}</span>`;
      header.insertBefore(meta, header.lastElementChild);
    }

    renameLabel('qb681-exam', '所屬考卷');
    renameLabel('qb681-correct', '正確答案');
    renameLabel('qb681-topic', '主題');
    renameLabel('qb681-subtopic', '子主題');
    renameLabel('qb681-objective', '學習目標');
    renameLabel('qb681-difficulty', '難度');
    renameLabel('qb681-cognitive', '認知層次');
    renameLabel('qb681-tags', '標籤（以逗號分隔）');
    renameLabel('qb681-source', '來源教材');
    renameLabel('qb681-rstype', '來源定位方式');
    renameLabel('qb681-start', '起始位置（頁／秒）');
    renameLabel('qb681-end', '結束位置（頁／秒）');
    renameLabel('qb681-status', '題目狀態');
    renameLabel('qb681-origin', '題目來源');

    translateSelect('qb681-difficulty', {easy: '簡單', medium: '中等', hard: '困難', standard: '一般'});
    translateSelect('qb681-cognitive', {remember: '記憶', understand: '理解', apply: '應用', analyze: '分析'});
    translateSelect('qb681-rstype', {page: '文件／PDF 頁碼', time: '影片時間'});
    translateSelect('qb681-status', {draft: '草稿', reviewed: '已審核', published: '已發布', retired: '已停用'});
    translateSelect('qb681-origin', {manual: '手動建立', ai_generated: 'AI 產生', imported: '匯入'});
    makeAnswerSelect();

    // Workflow state is controlled by review/publish actions, not by normal
    // question editing. Keep values in the DOM for the canonical payload but
    // remove them from the teacher-facing form.
    ['qb681-status', 'qb681-origin'].forEach(id => labelFor(id)?.classList.add('hidden'));

    const grid = question.closest('.grid');
    if (grid && !content.querySelector('[data-advanced-question-settings]')) {
      const details = document.createElement('details');
      details.dataset.advancedQuestionSettings = '1';
      details.className = 'md:col-span-2 rounded-xl border border-slate-200 bg-slate-50/70 p-3';
      details.innerHTML = '<summary class="cursor-pointer text-sm font-black text-slate-700">⚙️ 進階設定（選填）</summary><div data-advanced-body class="mt-3 grid gap-3 md:grid-cols-2"></div>';
      const advancedBody = details.querySelector('[data-advanced-body]');
      [
        'qb681-topic', 'qb681-subtopic', 'qb681-objective', 'qb681-difficulty',
        'qb681-cognitive', 'qb681-tags', 'qb681-source', 'qb681-rstype',
        'qb681-start', 'qb681-end', 'qb681-status', 'qb681-origin'
      ].forEach(id => {
        const label = labelFor(id);
        if (label) advancedBody.appendChild(label);
      });
      grid.appendChild(details);
    }

    const statusText = document.getElementById('qb681-status-text');
    const actions = statusText?.parentElement;
    if (actions) {
      actions.className = 'mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4';
      const buttons = [...actions.querySelectorAll('button')];
      const save = buttons.find(button => button.getAttribute('onclick')?.includes('assessment681SaveQuestion'));
      const preview = buttons.find(button => button.getAttribute('onclick')?.includes('assessment681PreviewSource'));
      if (save) save.textContent = '💾 儲存題目';
      if (preview) preview.textContent = '🔎 預覽教材來源';
      if (!actions.querySelector('[data-question-cancel]')) {
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.dataset.questionCancel = '1';
        cancel.className = 'rounded border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50';
        cancel.textContent = '取消';
        cancel.onclick = () => window.assessment681CloseQuestion?.();
        if (preview) actions.insertBefore(cancel, preview);
        else actions.appendChild(cancel);
      }
      if (questionId && !actions.querySelector('[data-question-delete]')) {
        const del = document.createElement('button');
        del.type = 'button';
        del.dataset.questionDelete = '1';
        del.className = 'ml-auto rounded border border-rose-200 bg-white px-4 py-2 text-sm font-bold text-rose-700 hover:bg-rose-50';
        del.textContent = '🗑️ 刪除此題';
        del.onclick = () => window.assessment681Delete?.(questionId);
        actions.appendChild(del);
      }
    }
  }

  function simplifyTabs() {
    const tabBox = document.getElementById('assessment-681-tabs');
    if (!tabBox) return;
    const names = {
      '考卷': '考卷管理',
      '題庫': '設計題目',
      'AI 出題': 'AI 輔助出題',
      '出題藍圖': '進階抽題',
      '題目分析': '題目分析'
    };
    [...tabBox.querySelectorAll('button')].forEach(button => {
      const text = button.textContent.trim();
      if (names[text]) button.textContent = names[text];
      if (['進階抽題', '題目分析'].includes(button.textContent.trim())) {
        button.classList.add('opacity-80');
        button.title = '進階工具';
      }
    });
    const title = document.querySelector('#assessment-681 h4');
    if (title) title.textContent = '📝 出題與考卷';
    const intro = document.querySelector('#assessment-681 h4 + p');
    if (intro) intro.textContent = '先建立考卷，再設計題目；需要時再使用 AI 或進階抽題工具。';
  }

  function install() {
    if (typeof window.assessment681OpenQuestion === 'function' && !window.assessment681OpenQuestion.__teacher71Wrapped) {
      const originalOpen = window.assessment681OpenQuestion;
      const wrappedOpen = function (questionId) {
        const result = originalOpen(questionId);
        requestAnimationFrame(() => simplifyQuestionDrawer(questionId));
        return result;
      };
      wrappedOpen.__teacher71Wrapped = true;
      window.assessment681OpenQuestion = wrappedOpen;
    }

    if (typeof window.assessment681SaveQuestion === 'function' && !window.assessment681SaveQuestion.__teacher71Wrapped) {
      const originalSave = window.assessment681SaveQuestion;
      const wrappedSave = async function () {
        const result = await originalSave();
        if (result) window.assessment681CloseQuestion?.();
        return result;
      };
      wrappedSave.__teacher71Wrapped = true;
      window.assessment681SaveQuestion = wrappedSave;
    }

    // The Question Bank 2.0 DELETE endpoint needs the category to resolve a
    // group-scoped teacher safely. Look up the row first, then include the
    // category in the DELETE request so RBAC can authorize the correct group.
    const wrappedDelete = async function (questionId) {
      if (!questionId || !confirm('確定刪除這一題？刪除後無法復原。')) return;
      try {
        const bank = await api('/api/question-bank');
        const item = (bank.items || []).find(row => String(row.id) === String(questionId));
        const category = String(item?.quizCategoryId || '').trim();
        const suffix = category ? `?quizCategoryId=${encodeURIComponent(category)}` : '';
        await api(`/api/question-bank/${encodeURIComponent(questionId)}${suffix}`, {method: 'DELETE'});
        window.assessment681CloseQuestion?.();
        await window.assessment681Refresh?.();
      } catch (error) {
        alert(error.message || '刪除失敗');
      }
    };
    wrappedDelete.__teacher71Wrapped = true;
    window.assessment681Delete = wrappedDelete;

    simplifyTabs();
    const tabs = document.getElementById('assessment-681-tabs');
    if (tabs && !tabs.dataset.teacher71Observed) {
      tabs.dataset.teacher71Observed = '1';
      new MutationObserver(simplifyTabs).observe(tabs, {childList: true});
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(install, 0), {once: true});
  } else {
    setTimeout(install, 0);
  }
})();

/* Load the unified teacher content studio as a presentation-only companion.
 * Keeping this composition next to the teacher-first authoring overlay avoids
 * adding business logic to legacy compatibility bundles; all mutations remain
 * owned by their existing canonical modules.
 */
(function(){
  'use strict';
  if (document.querySelector('script[src*="/teacher-content-studio-71.js"]')) return;
  const script = document.createElement('script');
  script.src = '/teacher-content-studio-71.js?v=7115';
  script.defer = true;
  document.head.appendChild(script);
})();
