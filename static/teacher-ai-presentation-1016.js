/* Reviewed AI slides -> Worker PPTX -> Phase 4 quality-gated publishing workspace. */
(async function () {
  'use strict';
  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  if (!['clinical_teacher', 'group_leader', 'education_admin', 'system_admin'].some(role => roles.has(role))) return;

  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  let capabilities = {};
  let qualityRulesetVersion = '';

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
    if (!response.ok) {
      const error = new Error(data.error || 'AI PowerPoint 服務無法回應');
      error.payload = data;
      throw error;
    }
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
    qualityRulesetVersion = state.qualityRulesetVersion || '';
    const badge = $('teacher-ai-presentation-provider-1016');
    if (badge) badge.textContent = state.storage?.available ? `AI Worker｜${state.storage.backend}｜${qualityRulesetVersion || 'quality rules'}` : `尚未啟用｜${state.storage?.reason || ''}`;
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
      if (job.status === 'completed') { note('✅ PowerPoint 已保存並完成 Phase 4 品質檢查。'); await loadPresentations(); return; }
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
  function qualityBadge(item) {
    const status = item.qualityStatus || item.qualityManifest?.status || 'pass';
    const warnings = Number(item.qualityManifest?.warningCount || 0);
    const errors = Number(item.qualityManifest?.errorCount || 0);
    if (status === 'error') return `<span class="rounded-full bg-rose-100 px-2 py-1 text-[11px] font-bold text-rose-800">品質阻擋 ${errors}</span>`;
    if (status === 'warning') return `<span class="rounded-full bg-amber-100 px-2 py-1 text-[11px] font-bold text-amber-800">品質警告 ${warnings}</span>`;
    return '<span class="rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-bold text-emerald-800">品質通過</span>';
  }
  function card(item) {
    const approvals = item.approvedBy ? `｜核准：${escape(item.approvedBy)}` : '';
    const metrics = item.renderMetrics || {};
    const duration = Number(metrics.durationMs || 0) > 0 ? `${(Number(metrics.durationMs) / 1000).toFixed(1)} 秒` : '—';
    const attempts = Number(metrics.attempts || 0);
    const lastError = metrics.lastError ? `｜最後錯誤：${escape(metrics.lastError)}` : '';
    return `<article class="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2" data-presentation-id="${escape(item.id)}">
      <div class="flex flex-wrap items-center justify-between gap-2"><div><b class="text-sm text-slate-950">${escape(item.title || 'AI 教學投影片')}</b><p class="text-[11px] text-slate-500">${escape(item.id)}｜revision ${Number(item.revisionNumber || 1)}｜${escape(item.status || 'draft')}${approvals}</p></div><div class="flex flex-wrap items-center gap-2">${qualityBadge(item)}<span class="text-[11px] font-bold ${item.artifactReady ? 'text-emerald-700' : 'text-amber-700'}">${item.artifactReady ? 'PPTX 已就緒' : '等待 AI Worker artifact'}</span></div></div>
      <p class="text-[11px] text-slate-500">建立：${escape(item.createdBy || '—')}｜更新：${escape(item.updatedBy || '—')}｜render ${escape(duration)}｜attempts ${attempts}${lastError}</p>
      <div class="flex flex-wrap gap-2 text-xs"><a class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-bold text-indigo-700 ${item.artifactReady ? '' : 'pointer-events-none opacity-40'}" href="/api/ai-presentations/${encodeURIComponent(item.id)}/download">⬇️ 草稿／指定版本</a><button type="button" data-action="quality" class="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 font-bold text-emerald-700">品質檢查</button><button type="button" data-action="regenerate" class="rounded-lg border border-cyan-200 bg-white px-3 py-1.5 font-bold text-cyan-700">依最新規則重新產生</button><button type="button" data-action="history" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">版本歷史</button><button type="button" data-action="provenance" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">來源追溯</button><button type="button" data-action="revision" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">建立文字修訂版</button><button type="button" data-action="structure" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">版型／區塊編輯</button>${item.status === 'draft' ? '<button type="button" data-action="approve" class="rounded-lg bg-emerald-700 px-3 py-1.5 font-bold text-white">教師核准</button>' : ''}${item.status === 'approved' ? '<button type="button" data-action="publish" class="rounded-lg bg-violet-700 px-3 py-1.5 font-bold text-white">正式發布</button>' : ''}${item.status === 'published' ? `<a class="rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 font-bold text-violet-800" href="/api/ai-presentation-families/${encodeURIComponent(item.presentationFamilyId)}/published/download">⬇️ 目前正式版</a>` : ''}</div>
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
      if (button.dataset.action === 'quality') {
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/quality`);
        const output = cardNode.querySelector('[data-provenance]');
        output.textContent = JSON.stringify({quality:data.quality, renderMetrics:data.renderMetrics, publishable:data.publishable}, null, 2);
        output.classList.toggle('hidden'); return;
      }
      if (button.dataset.action === 'regenerate') {
        if (!confirm(`確認依 ${qualityRulesetVersion || '最新品質規則'} 建立新的 immutable revision 並重新產生嗎？`)) return;
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/regenerate`, {method:'POST'});
        note(data.replayed ? '已存在相同的 regenerate 工作，沿用原工作。' : '已建立新的 Phase 4 revision，AI Worker 正在重新產生。');
        if (data.job?.id) await poll(data.job.id); else await loadPresentations(); return;
      }
      if (button.dataset.action === 'provenance') {
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/provenance`);
        const output = cardNode.querySelector('[data-provenance]'); output.textContent = JSON.stringify(data.provenance || {}, null, 2); output.classList.toggle('hidden'); return;
      }
      if (button.dataset.action === 'history') {
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/history`);
        const output = cardNode.querySelector('[data-provenance]');
        const published = data.published ? `目前正式版：r${data.published.revisionNumber}（${data.published.publishedAt || '已發布'}）` : '目前尚未正式發布';
        output.textContent = `${published}\n` + (data.revisions || []).map(revision => `r${revision.revisionNumber}｜${revision.status}｜品質 ${revision.qualityStatus || '—'}｜${revision.updatedBy || '—'}｜${revision.updatedAt || ''}｜${revision.id}`).join('\n');
        output.classList.remove('hidden'); return;
      }
      if (button.dataset.action === 'approve') {
        if (!confirm('確認已檢查此 PowerPoint revision 的內容與來源，並核准嗎？')) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}/approve`, {method:'POST'}); note('✅ 已核准這個 revision。'); await loadPresentations(); return;
      }
      if (button.dataset.action === 'revision') {
        const title = prompt('新 revision 的標題（會由 AI Worker 重新產生 PPTX）'); if (title === null) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title})}); note('已建立新的 draft revision，AI Worker 正在重新產生 artifact。'); await loadPresentations(); return;
      }
      if (button.dataset.action === 'structure') {
        const current = await api(`/api/ai-presentations/${encodeURIComponent(id)}`);
        const raw = prompt('編輯 JSON：layout 僅支援 title/section/content/image/comparison/table/summary；圖片只能使用 shared-provider checksum asset。Phase 4 會自動選版型、拆頁與檢查 overflow。', JSON.stringify({title:current.title, slides:current.slides}, null, 2));
        if (raw === null) return;
        let payload;
        try { payload = JSON.parse(raw); } catch (_) { throw new Error('版型／內容 JSON 格式不正確。'); }
        await api(`/api/ai-presentations/${encodeURIComponent(id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
        note('已建立新的 immutable layout／內容 revision，AI Worker 正在重新產生。'); await loadPresentations(); return;
      }
      if (button.dataset.action === 'publish') {
        const publicationMaterialId = $('teacher-ai-presentation-material-1016')?.value.trim();
        if (!publicationMaterialId) throw new Error('請先填入同組、同範圍且已保存到 shared provider 的正式教材 ID。');
        const check = await api(`/api/ai-presentations/${encodeURIComponent(id)}/quality`);
        if (check.quality?.status === 'error') throw new Error('品質檢查有阻擋錯誤，請先修正或重新產生。');
        let acknowledgeWarnings = false;
        if (check.quality?.status === 'warning') {
          const codes = (check.quality.warnings || []).map(item => item.code).join('、');
          if (!confirm(`此版本有品質警告：${codes || '請人工檢查'}。確認已檢視並仍要正式發布嗎？`)) return;
          acknowledgeWarnings = true;
        } else if (!confirm('確認以此已核准 revision 建立不可變的正式發布快照嗎？')) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}/publish-link`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({publicationMaterialId, acknowledgeWarnings})});
        note('✅ 已建立品質檢核後的正式發布快照；舊版不會被覆寫。'); await loadPresentations(); return;
      }
      const file = cardNode.querySelector('[data-upload]')?.files?.[0];
      if (!file) throw new Error('請先選擇教師修正版 .pptx。');
      const body = new FormData(); body.append('file', file);
      await api(`/api/ai-presentations/${encodeURIComponent(id)}/reupload`, {method:'POST', body}); note('✅ 教師修正版已保存為新的 draft revision；發布前會要求人工品質確認。'); await loadPresentations();
    } catch (error) { note(error.message, true); }
  }
  function install() {
    const host = $('teacher-media-production-1014'); if (!host || $('teacher-ai-presentation-1016')) return false;
    const panel = document.createElement('section'); panel.id = 'teacher-ai-presentation-1016'; panel.className = 'bg-white border border-violet-200 rounded-2xl p-5 shadow-sm space-y-4';
    panel.innerHTML = `<div class="flex flex-col lg:flex-row lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-violet-700">AI POWERPOINT · PHASE 4</p><h4 class="text-lg font-black text-slate-950">🖥️ 教學品質自動化 PowerPoint</h4><p class="mt-1 text-xs text-slate-500">AI Worker 自動選版型、拆分過長文字／表格、適配圖片並產生品質檢核；發布仍保留教師核准、不可變版本與來源追溯。</p></div><span id="teacher-ai-presentation-provider-1016" class="rounded-full bg-violet-50 px-3 py-1.5 text-[11px] font-bold text-violet-800">檢查服務中…</span></div><div class="grid md:grid-cols-3 gap-3"><label class="text-xs font-bold text-slate-600">已核准 slides 草稿 ID<input id="teacher-ai-presentation-draft-1016" class="learning-input mt-1" placeholder="aidraft-…"></label><label class="text-xs font-bold text-slate-600">可選 PowerPoint 範本<select id="teacher-ai-presentation-template-1016" class="learning-input mt-1"><option>讀取中…</option></select></label><label class="text-xs font-bold text-slate-600">正式教材 ID（篩選／發布）<input id="teacher-ai-presentation-material-1016" class="learning-input mt-1" placeholder="mat-…"></label></div><div class="flex flex-wrap gap-3"><button id="teacher-ai-presentation-generate-1016" type="button" class="rounded-xl bg-violet-700 px-5 py-2.5 text-xs font-black text-white disabled:opacity-40">建立 PowerPoint</button><button id="teacher-ai-presentation-refresh-1016" type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-black text-slate-700">讀取版本</button><span id="teacher-ai-presentation-status-1016" class="self-center text-xs text-slate-600">先由 AI 教材助手建立並核准投影片大綱。</span></div><div id="teacher-ai-presentation-results-1016" class="space-y-2"></div><p class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] text-amber-900"><b>Phase 4 品質 gate：</b>blocking error 無法發布；warning 必須由授權發布者明確確認。外部 URL、iframe、秘密、Worker 本機路徑與內部 storage key 不會顯示在學生可見投影片。</p>`;
    host.prepend(panel); panel.addEventListener('click', action); $('teacher-ai-presentation-generate-1016').addEventListener('click', generate); $('teacher-ai-presentation-refresh-1016').addEventListener('click', () => void loadPresentations().catch(error => note(error.message, true)));
    void Promise.all([loadStatus(), loadTemplates(), loadPresentations()]).catch(error => note(error.message, true)); return true;
  }
  if (!install()) { const observer = new MutationObserver(() => { if (install()) observer.disconnect(); }); observer.observe(document.body, {childList:true, subtree:true}); }
})();
