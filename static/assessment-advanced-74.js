/* Teacher 7.4 · Advanced assessment tools only.
 *
 * This module intentionally owns only the two capabilities that had no other
 * canonical frontend owner: exam blueprint snapshots and item analytics.
 * Exam/question CRUD and AI generation remain owned by the canonical admin-*
 * modules. Authorization is server-side session RBAC.
 */
(function () {
  'use strict';

  const esc = value => (window.escapeHtml
    ? window.escapeHtml(String(value ?? ''))
    : String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state = {tab:'blueprint', categories:[], questions:[], blueprint:null};

  async function api(url, options = {}) {
    const headers = {...(options.headers || {})};
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    const response = await fetch(url, {...options, headers, credentials:'same-origin'});
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.href = `/login?next=${next}`;
      throw new Error('登入已逾時，請重新登入。');
    }
    if (response.status === 403) throw new Error(body.error || '此帳號沒有這項操作權限。');
    if (!response.ok) throw new Error(body.error || '操作失敗');
    return body;
  }

  function scope() {
    return {
      area: document.getElementById('admin-quiz-area')?.value || window.currentTrainingArea || 'internal',
      group: document.getElementById('admin-quiz-group')?.value || window.currentGroupKey || 'grpBio'
    };
  }

  function root() { return document.getElementById('assessment-advanced-74'); }
  function body() { return document.getElementById('assessment-advanced-body-74'); }

  function ensurePanel() {
    let panel = root();
    if (panel) return panel;
    const canonical = document.getElementById('admin-quiz-workspace');
    if (!canonical) return null;
    panel = document.createElement('section');
    panel.id = 'assessment-advanced-74';
    panel.className = 'mt-5 rounded-2xl border border-slate-200 bg-white shadow-sm';
    panel.innerHTML = `
      <details id="assessment-advanced-details-74">
        <summary class="cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3">
          <span><b class="text-sm text-slate-900">🧪 進階考核工具</b><span class="ml-2 text-xs text-slate-500">出題藍圖與題目分析</span></span>
          <span class="text-xs font-bold text-indigo-700">展開</span>
        </summary>
        <div class="border-t border-slate-100 p-4">
          <div class="flex flex-wrap gap-2 mb-4">
            <button type="button" data-advanced-tab="blueprint" class="rounded-lg px-3 py-2 text-xs font-bold">🎯 出題藍圖</button>
            <button type="button" data-advanced-tab="analytics" class="rounded-lg px-3 py-2 text-xs font-bold">📈 題目分析</button>
          </div>
          <div id="assessment-advanced-body-74"></div>
        </div>
      </details>`;
    canonical.appendChild(panel);
    panel.addEventListener('click', event => {
      const tab = event.target.closest('[data-advanced-tab]')?.dataset.advancedTab;
      if (tab) { state.tab = tab; render(); }
      if (event.target.closest('[data-blueprint-create]')) createBlueprint();
      if (event.target.closest('[data-blueprint-publish]')) publishBlueprint();
      if (event.target.closest('[data-analytics-load]')) loadAnalytics();
    });
    render();
    return panel;
  }

  function examOptions(selected='') {
    if (!state.categories.length) return '<option value="">尚無考卷</option>';
    return state.categories.map(item => `<option value="${esc(item.id)}" ${String(item.id)===String(selected)?'selected':''}>${esc(item.title || item.id)}</option>`).join('');
  }

  function questionOptions(selected='') {
    const rows = state.questions.filter(item => item.id);
    if (!rows.length) return '<option value="">尚無可分析題目</option>';
    return rows.map(item => `<option value="${esc(item.id)}" ${String(item.id)===String(selected)?'selected':''}>${esc((item.question || item.id).slice(0,90))}</option>`).join('');
  }

  function tabButtonState() {
    root()?.querySelectorAll('[data-advanced-tab]').forEach(button => {
      const active = button.dataset.advancedTab === state.tab;
      button.className = active
        ? 'rounded-lg bg-indigo-700 px-3 py-2 text-xs font-bold text-white'
        : 'rounded-lg bg-slate-100 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-200';
    });
  }

  function render() {
    const host = body(); if (!host) return;
    tabButtonState();
    if (state.tab === 'analytics') {
      host.innerHTML = `
        <div class="rounded-xl border border-sky-100 bg-sky-50/40 p-4">
          <h5 class="font-black text-sky-950">📈 題目分析</h5>
          <p class="mt-1 text-xs text-sky-700">只讀取既有作答統計，不修改題目。</p>
          <label class="mt-4 block text-xs font-bold text-slate-700">題目
            <select id="advanced-analytics-question-74" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">${questionOptions()}</select>
          </label>
          <div class="mt-3 flex items-center gap-3 flex-wrap">
            <button type="button" data-analytics-load class="rounded-lg bg-sky-700 px-3 py-2 text-xs font-bold text-white">讀取分析</button>
            <span id="advanced-analytics-status-74" class="text-xs text-slate-500"></span>
          </div>
          <div id="advanced-analytics-result-74" class="mt-3 text-sm text-slate-700"></div>
        </div>`;
      return;
    }
    host.innerHTML = `
      <div class="rounded-xl border border-teal-100 bg-teal-50/40 p-4">
        <h5 class="font-black text-teal-950">🎯 出題藍圖</h5>
        <p class="mt-1 text-xs text-teal-700">建立配額規則後，由伺服器保存與發布不可變快照；不在這裡建立或編輯題目。</p>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <label class="text-xs font-bold text-slate-700">考卷<select id="advanced-blueprint-exam-74" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">${examOptions()}</select></label>
          <label class="text-xs font-bold text-slate-700">總題數<input id="advanced-blueprint-count-74" type="number" min="1" value="10" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm"></label>
          <label class="text-xs font-bold text-slate-700">主題配額 JSON<textarea id="advanced-blueprint-topic-74" rows="3" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 font-mono text-xs">{}</textarea></label>
          <label class="text-xs font-bold text-slate-700">難度配額 JSON<textarea id="advanced-blueprint-difficulty-74" rows="3" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 font-mono text-xs">{}</textarea></label>
          <label class="text-xs font-bold text-slate-700">認知層次配額 JSON<textarea id="advanced-blueprint-cognitive-74" rows="3" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 font-mono text-xs">{}</textarea></label>
          <label class="text-xs font-bold text-slate-700">排除最近題數<input id="advanced-blueprint-recent-74" type="number" min="0" value="0" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm"></label>
          <label class="text-xs font-bold text-slate-700">題目分析加權
            <select id="advanced-blueprint-quality-74" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm">
              <option value="off" selected>關閉（維持原選題）</option>
              <option value="balanced">平衡模式（難度／鑑別度／誘答／曝光）</option>
            </select>
            <span class="mt-1 block text-[10px] font-normal text-slate-500">資料不足的題目保持中性權重；不會繞過配額或直接淘汰題目。</span>
          </label>
        </div>
        <div class="mt-3 flex items-center gap-2 flex-wrap">
          <button type="button" data-blueprint-create class="rounded-lg bg-teal-700 px-3 py-2 text-xs font-bold text-white">建立藍圖</button>
          <button type="button" data-blueprint-publish class="hidden rounded-lg bg-indigo-700 px-3 py-2 text-xs font-bold text-white">發布不可變快照</button>
          <span id="advanced-blueprint-status-74" class="text-xs text-slate-500"></span>
        </div>
      </div>`;
  }

  function parseObject(id) {
    try {
      const value = JSON.parse(document.getElementById(id)?.value || '{}');
      if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error();
      return value;
    } catch (_) {
      throw new Error('配額必須是 JSON 物件，例如 {"血液": 3}');
    }
  }

  async function refresh() {
    const panel = ensurePanel(); if (!panel) return;
    const {area, group} = scope();
    try {
      const [categories, bank] = await Promise.all([
        api(`/api/quiz-categories/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`),
        api('/api/question-bank')
      ]);
      state.categories = Array.isArray(categories) ? categories : [];
      state.questions = Array.isArray(bank?.items) ? bank.items : [];
      render();
    } catch (error) {
      const host = body();
      if (host) host.innerHTML = `<p class="text-xs text-rose-600">❌ ${esc(error.message)}</p>`;
    }
  }

  async function createBlueprint() {
    const out = document.getElementById('advanced-blueprint-status-74');
    try {
      const quizCategoryId = document.getElementById('advanced-blueprint-exam-74')?.value || '';
      if (!quizCategoryId) throw new Error('請先選擇考卷');
      if (out) out.textContent = '⏳ 建立藍圖中…';
      state.blueprint = await api('/api/exam-blueprints', {
        method:'POST',
        body:JSON.stringify({
          quizCategoryId,
          questionCount:Math.max(1, Number(document.getElementById('advanced-blueprint-count-74')?.value || 1)),
          quotas:{
            topic:parseObject('advanced-blueprint-topic-74'),
            difficulty:parseObject('advanced-blueprint-difficulty-74'),
            cognitive_level:parseObject('advanced-blueprint-cognitive-74')
          },
          qualityMode:document.getElementById('advanced-blueprint-quality-74')?.value || 'off',
          excludeRecent:Math.max(0, Number(document.getElementById('advanced-blueprint-recent-74')?.value || 0))
        })
      });
      if (out) out.textContent = state.blueprint?.qualityMode === 'balanced'
        ? '✅ 藍圖已建立；已啟用版本化題目分析平衡加權，可發布不可變快照。'
        : '✅ 藍圖已建立；可發布不可變快照。';
      root()?.querySelector('[data-blueprint-publish]')?.classList.remove('hidden');
    } catch (error) {
      if (out) out.textContent = `❌ ${error.message}`;
    }
  }

  async function publishBlueprint() {
    const out = document.getElementById('advanced-blueprint-status-74');
    const id = state.blueprint?.id;
    if (!id) { if (out) out.textContent = '❌ 請先建立藍圖'; return; }
    try {
      if (out) out.textContent = '⏳ 建立快照中…';
      const snapshot = await api(`/api/exam-blueprints/${encodeURIComponent(id)}/publish`, {method:'POST', body:'{}'});
      if (out) out.textContent = `✅ 不可變快照已建立，共 ${Number(snapshot.questionCount || 0)} 題。`;
    } catch (error) {
      if (out) out.textContent = `❌ ${error.message}`;
    }
  }

  async function loadAnalytics() {
    const out = document.getElementById('advanced-analytics-status-74');
    const box = document.getElementById('advanced-analytics-result-74');
    const id = document.getElementById('advanced-analytics-question-74')?.value || '';
    if (!id) { if (out) out.textContent = '請先選擇題目'; return; }
    try {
      if (out) out.textContent = '⏳ 讀取中…';
      const data = await api(`/api/questions/${encodeURIComponent(id)}/analytics`);
      if (out) out.textContent = '';
      if (!data.sufficientData) {
        if (box) box.textContent = '資料不足，暫不進行品質判定。';
        return;
      }
      const discrimination=data.discriminationD==null?'資料不足':Number(data.discriminationD).toFixed(2);
      const averageSeconds=data.averageResponseSeconds==null?'尚無 timing':`${Number(data.averageResponseSeconds).toFixed(1)} 秒`;
      if (box) box.innerHTML = `<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"><div class="rounded-lg bg-white p-3"><b>曝光／作答次數</b><div>${Number(data.exposureCount || data.attemptCount || 0)}</div></div><div class="rounded-lg bg-white p-3"><b>難度 P（答對率）</b><div>${Math.round(Number(data.difficultyP ?? data.correctRate ?? 0) * 100)}%</div></div><div class="rounded-lg bg-white p-3"><b>鑑別度 D</b><div>${esc(discrimination)}</div></div><div class="rounded-lg bg-white p-3"><b>平均作答時間</b><div>${esc(averageSeconds)}</div></div></div><div class="mt-2 rounded-lg bg-white p-3 text-xs"><b>選項選擇次數：</b>${esc(JSON.stringify(data.optionSelectionCounts || {}))}<br><b>誘答選項分布：</b>${esc(JSON.stringify(data.distractorDistribution || {}))}</div>`;
    } catch (error) {
      if (out) out.textContent = `❌ ${error.message}`;
    }
  }

  async function open(tab='blueprint') {
    await window.openAdminWorkspace?.('assessment');
    const panel = ensurePanel(); if (!panel) return;
    state.tab = tab === 'analytics' ? 'analytics' : 'blueprint';
    panel.querySelector('details').open = true;
    await refresh();
    panel.scrollIntoView({behavior:'smooth', block:'start'});
  }

  function install() {
    if (!ensurePanel()) {
      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        if (ensurePanel() || tries > 40) clearInterval(timer);
      }, 100);
    }
    document.getElementById('admin-quiz-area')?.addEventListener('change', refresh);
    document.getElementById('admin-quiz-group')?.addEventListener('change', refresh);
  }

  window.AssessmentAdvanced74 = Object.freeze({open, refresh});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
