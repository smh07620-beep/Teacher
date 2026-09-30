/* Reviewed AI slides -> Worker PPTX -> versioned teacher review workspace. */
(async function () {
  'use strict';
  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  if (!['clinical_teacher', 'group_leader', 'education_admin', 'system_admin'].some(role => roles.has(role))) return;

  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  let capabilities = {};

  function scope() {
    const query = new URLSearchParams(window.location.search);
    return {group: query.get('group') || window.currentGroupKey || 'grpBio', area: query.get('area') || window.currentTrainingArea || 'internal'};
  }
  function note(message, bad = false) {
    const node = $('teacher-ai-presentation-status-1016');
    if (!node) return;
    node.textContent = message;
    node.className = bad ? 'text-xs font-bold text-rose-700' : 'text-xs text-slate-600';
  }
  async function api(path, options) {
    const response = await fetch(path, Object.assign({credentials:'same-origin', cache:'no-store'}, options));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'AI PowerPoint 服務無法回應');
    return data;
  }
  function setBusy(value) {
    ['teacher-ai-presentation-generate-1016', 'teacher-ai-presentation-refresh-1016'].forEach(id => {
      const button = $(id); if (button) button.disabled = value;
    });
  }
  async function loadStatus() {
    const state = await api('/api/ai-presentations/status');
    capabilities = state.capabilities || {};
    const badge = $('teacher-ai-presentation-provider-1016');
    if (badge) badge.textContent = state.storage?.available ? `AI Worker｜${state.storage.backend} durable provider` : `尚未啟用｜${state.storage?.reason || ''}`;
    const generate = $('teacher-ai-presentation-generate-1016');
    if (generate) generate.disabled = !state.storage?.available || !capabilities['presentation.create'];
  }
  async function loadTemplates() {
    const select = $('teacher-ai-presentation-template-1016');
    if (!select) return;
    const selected = select.value;
    const current = scope();
    const templates = await api(`/api/ai-presentation-templates?group=${encodeURIComponent(current.group)}&area=${encodeURIComponent(current.area)}`);
    select.innerHTML = '<option value="">不使用範本</option>';
    templates.forEach(template => {
      const option = document.createElement('option');
      option.value = template.id; option.textContent = template.name || template.id; select.appendChild(option);
    });
    if ([...select.options].some(option => option.value === selected)) select.value = selected;
  }
  async function poll(jobId) {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const job = await api(`/api/ai-presentations/jobs/${encodeURIComponent(jobId)}`);
      note(`${job.progressStage || job.status}｜${Math.round(Number(job.progressPercent || 0))}%${job.progressDetail ? `｜${job.progressDetail}` : ''}`);
      if (job.status === 'completed') { note('✅ PowerPoint 已保存；請下載檢查、必要時上傳教師修正版，再核准。'); await loadPresentations(); return; }
      if (job.status === 'failed') throw new Error(job.error || 'PowerPoint 產生失敗');
      await new Promise(resolve => setTimeout(resolve, 1800));
    }
    throw new Error('等待逾時；工作可能仍在 AI Worker 背景處理。');
  }
  async function generate() {
    const draftId = $('teacher-ai-presentation-draft-1016')?.value.trim();
    if (!draftId) return note('請填入已由教師核准的「投影片大綱」AI 草稿 ID。', true);
    setBusy(true);
    try {
      const job = await api('/api/ai-presentations/generate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({draftId, templateId:$('teacher-ai-presentation-template-1016')?.value || ''})});
      await poll(job.id);
    } catch (error) { note(`建立 PowerPoint 失敗：${error.message}`, true); }
    finally { setBusy(false); }
  }
  function card(item) {
    const approvals = item.approvedBy ? `｜核准：${escape(item.approvedBy)}` : '';
    return `<article class="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2" data-presentation-id="${escape(item.id)}">
      <div class="flex flex-wrap items-center justify-between gap-2"><div><b class="text-sm text-slate-950">${escape(item.title || 'AI 教學投影片')}</b><p class="text-[11px] text-slate-500">${escape(item.id)}｜revision ${Number(item.revisionNumber || 1)}｜${escape(item.status || 'draft')}${approvals}</p></div><span class="text-[11px] font-bold ${item.artifactReady ? 'text-emerald-700' : 'text-amber-700'}">${item.artifactReady ? 'PPTX 已就緒' : '等待 AI Worker artifact'}</span></div>
      <div class="flex flex-wrap gap-2 text-xs"><a class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-bold text-indigo-700 ${item.artifactReady ? '' : 'pointer-events-none opacity-40'}" href="/api/ai-presentations/${encodeURIComponent(item.id)}/download">⬇️ 下載 .pptx</a><button type="button" data-action="provenance" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">來源追溯</button><button type="button" data-action="revision" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">建立文字修訂版</button>${item.status === 'draft' ? '<button type="button" data-action="approve" class="rounded-lg bg-emerald-700 px-3 py-1.5 font-bold text-white">教師核准</button>' : ''}</div>
      <label class="block text-[11px] text-slate-600">教師修正版 .pptx（上傳後建立新 immutable revision）<input data-upload type="file" accept=".pptx" class="mt-1 block w-full text-xs"></label><button type="button" data-action="reupload" class="rounded-lg border border-violet-200 bg-white px-3 py-1.5 text-xs font-bold text-violet-700">上傳為新版本</button><pre data-provenance class="hidden overflow-auto rounded-lg bg-slate-900 p-2 text-[11px] text-slate-100"></pre></article>`;
  }
  async function loadPresentations() {
    const host = $('teacher-ai-presentation-results-1016'); if (!host) return;
    const materialId = $('teacher-ai-presentation-material-1016')?.value.trim() || '';
    const current = scope();
    const extra = materialId ? `&materialId=${encodeURIComponent(materialId)}` : '';
    const list = await api(`/api/ai-presentations?group=${encodeURIComponent(current.group)}${extra}`);
    host.innerHTML = list.length ? list.map(card).join('') : '<p class="text-xs text-slate-500">這個範圍尚未建立 AI PowerPoint revision。</p>';
  }
  async function action(event) {
    const button = event.target.closest('[data-action]'); if (!button) return;
    const cardNode = button.closest('[data-presentation-id]'); const id = cardNode?.dataset.presentationId;
    if (!id) return;
    try {
      if (button.dataset.action === 'provenance') {
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/provenance`);
        const output = cardNode.querySelector('[data-provenance]'); output.textContent = JSON.stringify(data.provenance || {}, null, 2); output.classList.toggle('hidden'); return;
      }
      if (button.dataset.action === 'approve') {
        if (!confirm('確認已檢查此 PowerPoint revision 的內容與來源，並核准嗎？')) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}/approve`, {method:'POST'}); note('✅ 已核准這個 revision。'); await loadPresentations(); return;
      }
      if (button.dataset.action === 'revision') {
        const title = prompt('新 revision 的標題（會由 AI Worker 重新產生 PPTX）'); if (title === null) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title})}); note('已建立新的 draft revision，AI Worker 正在重新產生 artifact。'); await loadPresentations(); return;
      }
      const file = cardNode.querySelector('[data-upload]')?.files?.[0];
      if (!file) throw new Error('請先選擇教師修正版 .pptx。');
      const body = new FormData(); body.append('file', file);
      await api(`/api/ai-presentations/${encodeURIComponent(id)}/reupload`, {method:'POST', body}); note('✅ 教師修正版已保存為新的 draft revision，仍需核准。'); await loadPresentations();
    } catch (error) { note(error.message, true); }
  }
  function install() {
    const host = $('teacher-media-production-1014'); if (!host || $('teacher-ai-presentation-1016')) return false;
    const panel = document.createElement('section'); panel.id = 'teacher-ai-presentation-1016'; panel.className = 'bg-white border border-violet-200 rounded-2xl p-5 shadow-sm space-y-4';
    panel.innerHTML = `<div class="flex flex-col lg:flex-row lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-violet-700">AI POWERPOINT · PHASE 2</p><h4 class="text-lg font-black text-slate-950">🖥️ 教材／SOP → 可追溯 PowerPoint</h4><p class="mt-1 text-xs text-slate-500">Web 僅編排工作與下載；AI Worker 將 .pptx 儲存至共用 provider。每次教師修訂皆為獨立 revision。</p></div><span id="teacher-ai-presentation-provider-1016" class="rounded-full bg-violet-50 px-3 py-1.5 text-[11px] font-bold text-violet-800">檢查服務中…</span></div><div class="grid md:grid-cols-3 gap-3"><label class="text-xs font-bold text-slate-600">已核准 slides 草稿 ID<input id="teacher-ai-presentation-draft-1016" class="learning-input mt-1" placeholder="aidraft-…"></label><label class="text-xs font-bold text-slate-600">可選 PowerPoint 範本<select id="teacher-ai-presentation-template-1016" class="learning-input mt-1"><option>讀取中…</option></select></label><label class="text-xs font-bold text-slate-600">正式教材 ID（篩選版本）<input id="teacher-ai-presentation-material-1016" class="learning-input mt-1" placeholder="mat-…"></label></div><div class="flex flex-wrap gap-3"><button id="teacher-ai-presentation-generate-1016" type="button" class="rounded-xl bg-violet-700 px-5 py-2.5 text-xs font-black text-white disabled:opacity-40">建立 PowerPoint</button><button id="teacher-ai-presentation-refresh-1016" type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-black text-slate-700">讀取版本</button><span id="teacher-ai-presentation-status-1016" class="self-center text-xs text-slate-600">先由 AI 教材助手建立並核准投影片大綱。</span></div><div id="teacher-ai-presentation-results-1016" class="space-y-2"></div><p class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] text-amber-900"><b>追溯與核准：</b>「來源追溯」只顯示 allow-list 的教材、草稿、工作、RAG chunk、模型與核准識別值；憑證與 Worker 路徑不會被保存或顯示。</p>`;
    host.prepend(panel); panel.addEventListener('click', action); $('teacher-ai-presentation-generate-1016').addEventListener('click', generate); $('teacher-ai-presentation-refresh-1016').addEventListener('click', () => void loadPresentations().catch(error => note(error.message, true)));
    void Promise.all([loadStatus(), loadTemplates(), loadPresentations()]).catch(error => note(error.message, true)); return true;
  }
  if (!install()) { const observer = new MutationObserver(() => { if (install()) observer.disconnect(); }); observer.observe(document.body, {childList:true, subtree:true}); }
})();
