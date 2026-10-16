/* AI PowerPoint studio: one guided authoring flow, backed by the existing Phase 4 APIs. */
/* Existing Phase 4 contracts remain available through the scoped server API:
 * /download, /provenance, /reupload and immutable revision history.  Advanced
 * version controls, including 版型／區塊編輯, stay secondary to the guided flow.
 */
(async function () {
  'use strict';
  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  if (!['clinical_teacher', 'group_leader', 'education_admin', 'system_admin'].some(role => roles.has(role))) return;
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  let selectedDraft = null, capabilities = {}, qualityRulesetVersion = '', serviceReady = false, serviceDiagnostic = '';
  let currentPresentation = null, currentPresentationId = '', presentationRows = [], publicationMaterials = [];
  function scope() { const q = new URLSearchParams(location.search); return {group:q.get('group') || window.currentGroupKey || 'grpBio', area:q.get('area') || window.currentTrainingArea || 'internal'}; }
  function note(message, bad = false) { const n = $('teacher-ai-presentation-status-1016'); if (n) { n.textContent = message; n.className = bad ? 'text-sm font-bold text-rose-700' : 'text-sm text-slate-600'; } }
  async function api(path, options = {}, timeoutMs = 15000) { const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs); try { const r = await fetch(path, Object.assign({credentials:'same-origin', cache:'no-store', signal:controller.signal}, options)); const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || 'AI PowerPoint 服務無法回應'); return d; } catch (error) { if (error?.name === 'AbortError') throw new Error('AI PowerPoint 服務回應逾時，已停止這次讀取；請按「讀取版本」重試。'); throw error; } finally { clearTimeout(timer); } }
  function setBusy(value) { ['teacher-ai-presentation-generate-1016','teacher-ai-presentation-refresh-1016','teacher-ai-presentation-create-material-1016'].forEach(id => { const b = $(id); if (b) b.disabled = value; }); }
  function syncDraft() {
    const approved = selectedDraft?.draftType === 'slides' && selectedDraft?.status === 'approved';
    const summary = $('teacher-ai-presentation-draft-summary-1016');
    if (summary) summary.textContent = selectedDraft ? `${selectedDraft.title || '投影片大綱'}｜${approved ? '已核准，可以建立投影片' : '請先在上方「第 3 步」儲存，並按「教師核准」'}` : '請先在上方「第 3 步」產生大綱、儲存，並按「教師核准」。';
    const generate = $('teacher-ai-presentation-generate-1016'); if (generate) generate.disabled = !approved || !capabilities['presentation.create'] || !serviceReady;
  }
  async function loadStatus() { const state = await api('/api/ai-presentations/status'); capabilities = state.capabilities || {}; qualityRulesetVersion = state.qualityRulesetVersion || ''; serviceReady = Boolean(state.ready); serviceDiagnostic = String(state.diagnostic?.message || 'PowerPoint 生產鏈尚未就緒。'); const badge = $('teacher-ai-presentation-provider-1016'); if (badge) badge.textContent = serviceReady ? '投影片製作服務：已就緒' : state.storage?.available ? '投影片製作服務：等待院內 AI 工作站回報' : `投影片製作服務：尚未啟用${state.storage?.reason ? '（' + state.storage.reason + '）' : ''}`; const flow = $('teacher-ai-presentation-flow-1016'); if (flow) flow.textContent = state.workflow?.ready ? '① 核准大綱 → ② 選版型 → ③ 系統產生投影片 → ④ 你檢查修改並核准 → ⑤ 發布或接續做影片' : serviceDiagnostic; syncDraft(); }
  async function loadTemplates() { const select = $('teacher-ai-presentation-template-1016'); if (!select) return; const prior = select.value, current = scope(), templates = await api(`/api/ai-presentation-templates?group=${encodeURIComponent(current.group)}&area=${encodeURIComponent(current.area)}`); select.replaceChildren(new Option('不使用版型', '')); templates.forEach(item => select.add(new Option(item.name || item.id, item.id))); if ([...select.options].some(o => o.value === prior)) select.value = prior; }
  function publicationTarget() {
    const id = String($('teacher-ai-presentation-publication-material-1016')?.value || '');
    return publicationMaterials.find(item => String(item.id || '') === id) || null;
  }
  function renderPublicationTarget() {
    const host = $('teacher-ai-presentation-publication-target-1016');
    const create = $('teacher-ai-presentation-create-material-1016');
    if (!host) return;
    if (!currentPresentation) {
      host.innerHTML = '<p class="text-xs text-slate-500">先按上面的「建立投影片」；系統會自動使用這次的來源與最新一版。</p>';
      if (create) create.classList.add('hidden');
      return;
    }
    const target = publicationTarget();
    if (target) {
      host.innerHTML = `<div class="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2"><div class="text-[11px] font-black text-emerald-800">發布目的地已自動帶入</div><div class="mt-1 text-sm font-bold text-slate-900">${escape(target.title || target.filename || '正式教材')}</div><div class="mt-1 text-[11px] text-slate-500">不需要再從舊教材清單重新選擇。</div></div>`;
      if (create) create.classList.add('hidden');
    } else {
      host.innerHTML = '<div class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"><b>尚未有本次正式教材。</b><div class="mt-1">目前 PowerPoint 仍會保留；先建立本次正式教材後即可發布，不會要求你從舊教材中挑一份。</div></div>';
      if (create) create.classList.remove('hidden');
    }
  }
  async function loadPublicationMaterials(preferred = '') {
    const input = $('teacher-ai-presentation-publication-material-1016');
    if (!input) return;
    const current = scope(), list = await api('/api/slides/admin');
    publicationMaterials = (Array.isArray(list) ? list : []).filter(item => item?.id && item.active !== false && !item.isBuiltin && item.group === current.group && item.area === current.area);
    const preferredId = String(preferred || selectedDraft?.publicationMaterialId || currentPresentation?.materialId || '');
    const resolved = publicationMaterials.find(item => String(item.id || '') === preferredId) || null;
    input.value = resolved ? String(resolved.id || '') : '';
    renderPublicationTarget();
  }
  async function poll(jobId) { const pollWait = AppApiClient.pollBackoff(); for (let i = 0; i < 180; i += 1) { const job = await api(`/api/ai-presentations/jobs/${encodeURIComponent(jobId)}`); note(`${job.progressStage || job.status}｜${Math.round(Number(job.progressPercent || 0))}%${job.progressDetail ? `｜${job.progressDetail}` : ''}`); if (job.status === 'completed') { note('✅ 投影片已完成，並通過品質檢查。'); currentPresentationId = ''; await loadPresentations({preferLatest:true}); return; } if (job.status === 'failed') throw new Error(job.error || '投影片產生失敗'); await pollWait(); } throw new Error('等待逾時；工作可能還在背景進行，請稍後按「重新讀取結果」確認。'); }
  async function generate() { if (!selectedDraft) window.dispatchEvent(new CustomEvent('teacher-ai-material-request-draft')); if (!selectedDraft || selectedDraft.draftType !== 'slides' || selectedDraft.status !== 'approved') return note('請先在上方「第 3 步」儲存大綱，並按「教師核准」。', true); if (!serviceReady) return note(serviceDiagnostic || 'AI 工作站目前沒有連線，暫時不能建立投影片。', true); setBusy(true); try { const job = await api('/api/ai-presentations/generate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({draftId:selectedDraft.id, templateId:$('teacher-ai-presentation-template-1016')?.value || ''})}); await poll(job.id); } catch (e) { note(`建立投影片失敗：${e.message}`, true); } finally { setBusy(false); syncDraft(); } }
  function qualityBadge(item) { const status = item.qualityStatus || item.qualityManifest?.status || 'pass'; return status === 'error' ? '<span class="rounded-full bg-rose-100 px-2 py-1 text-[11px] font-bold text-rose-800">品質阻擋</span>' : status === 'warning' ? '<span class="rounded-full bg-amber-100 px-2 py-1 text-[11px] font-bold text-amber-800">品質警告</span>' : '<span class="rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-bold text-emerald-800">品質通過</span>'; }
  function statusLabel(item) { return ({draft:'待教師核准',approved:'已核准',published:'已正式發布'})[String(item?.status || '')] || String(item?.status || 'draft'); }
  function currentCard(item) {
    const approve = item.status === 'draft' ? '<button type="button" data-action="approve" class="rounded-lg bg-emerald-700 px-3 py-1.5 font-black text-white">教師核准</button>' : '';
    const publish = item.status === 'approved' ? '<button type="button" data-action="publish" class="rounded-lg bg-violet-700 px-3 py-1.5 font-black text-white">正式發布這一版</button>' : '';
    const discard = item.status !== 'published' ? '<button type="button" data-action="discard" class="rounded-lg border border-rose-200 bg-white px-3 py-1.5 font-bold text-rose-700">捨棄這份</button>' : '';
    const published = item.status === 'published' ? '<span class="rounded-lg bg-emerald-50 px-3 py-1.5 font-bold text-emerald-800">✓ 已正式發布</span>' : '';
    return `<article class="rounded-xl border border-violet-200 bg-white p-4 space-y-3" data-presentation-id="${escape(item.id)}"><div class="flex flex-wrap items-start justify-between gap-3"><div><div class="text-[11px] font-black tracking-wide text-violet-700">目前工作中的投影片</div><b class="mt-1 block text-base text-slate-950">${escape(item.title || 'AI 教學投影片')}</b><p class="mt-1 text-xs text-slate-500">V${Number(item.revisionNumber || 1)} · ${escape(statusLabel(item))} · ${Number((item.slides || []).length)} 張${item.approvedBy ? ` · 核准：${escape(item.approvedBy)}` : ''}</p></div>${qualityBadge(item)}</div><div class="flex flex-wrap gap-2 text-xs"><a class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-bold text-indigo-700 ${item.artifactReady ? '' : 'pointer-events-none opacity-40'}" href="/api/ai-presentations/${encodeURIComponent(item.id)}/download">⬇️ 下載</a><button type="button" data-action="quality" class="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 font-bold text-emerald-700">品質檢查</button><button type="button" data-action="provenance" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-bold text-slate-700">來源追溯</button>${approve}${publish}${discard}${published}</div><pre data-output class="hidden overflow-auto rounded-lg bg-slate-900 p-2 text-[11px] text-slate-100"></pre></article>`;
  }
  function renderHistory() {
    const host = $('teacher-ai-presentation-history-list-1016');
    if (!host) return;
    if (!currentPresentation) {
      host.innerHTML = '<p class="text-xs text-slate-500">目前沒有版本歷史。</p>';
      return;
    }
    const family = String(currentPresentation.presentationFamilyId || currentPresentation.id || '');
    const rows = presentationRows
      .filter(item => String(item.presentationFamilyId || item.id || '') === family && String(item.id || '') !== String(currentPresentation.id || ''))
      .sort((a,b) => Number(b.revisionNumber || 0) - Number(a.revisionNumber || 0));
    host.innerHTML = rows.length ? rows.map(item => `<div class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2"><div><b class="text-xs text-slate-900">V${Number(item.revisionNumber || 1)} · ${escape(item.title || 'AI 教學投影片')}</b><div class="mt-0.5 text-[11px] text-slate-500">${escape(statusLabel(item))} · ${escape(item.updatedAt || '')}</div></div><button type="button" data-use-presentation="${escape(item.id || '')}" class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-700">改用此版本</button></div>`).join('') : '<p class="text-xs text-slate-500">這份簡報目前沒有較舊 revision。</p>';
  }
  function renderCurrentPresentation() {
    const host = $('teacher-ai-presentation-results-1016');
    if (!host) return;
    host.innerHTML = currentPresentation ? currentCard(currentPresentation) : '<p class="rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">這份教材還沒有做出投影片。完成「第 5 步」後，最新一版會自動出現在這裡。</p>';
    renderHistory();
    renderPublicationTarget();
  }
  function chooseCurrentPresentation(rows, preferLatest = false) {
    const exactDraft = selectedDraft?.id ? rows.filter(item => String(item.draftId || '') === String(selectedDraft.id)) : [];
    const sourceRows = selectedDraft?.materialId ? rows.filter(item => String(item.materialId || '') === String(selectedDraft.materialId)) : [];
    const candidates = exactDraft.length ? exactDraft : sourceRows;
    candidates.sort((a,b) => Number(b.revisionNumber || 0) - Number(a.revisionNumber || 0) || String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
    let chosen = !preferLatest && currentPresentationId ? candidates.find(item => String(item.id || '') === currentPresentationId) : null;
    if (!chosen) chosen = candidates[0] || null;
    currentPresentation = chosen;
    currentPresentationId = String(chosen?.id || '');
  }
  async function loadPresentations(options = {}) {
    if (!selectedDraft?.id && !selectedDraft?.materialId) {
      presentationRows = []; currentPresentation = null; currentPresentationId = '';
      renderCurrentPresentation();
      window.dispatchEvent(new CustomEvent('teacher-ai-presentation-rendered-f5',{detail:{count:0,materialId:''}}));
      return;
    }
    const current = scope(), materialId = selectedDraft?.materialId || '';
    const list = await api(`/api/ai-presentations?group=${encodeURIComponent(current.group)}${materialId ? `&materialId=${encodeURIComponent(materialId)}` : ''}`);
    presentationRows = Array.isArray(list) ? list : [];
    chooseCurrentPresentation(presentationRows, Boolean(options.preferLatest));
    renderCurrentPresentation();
    await loadPublicationMaterials().catch(() => { renderPublicationTarget(); });
    window.dispatchEvent(new CustomEvent('teacher-ai-presentation-rendered-f5',{detail:{count:presentationRows.length,materialId,currentPresentationId}}));
  }
  // 品質檢查結果：用老師看得懂的話列出，不顯示程式用的原始資料。
  const QUALITY_TEXT = {
    TEXT_SPLIT:'文字太多，已自動分成多張', TABLE_SPLIT:'表格太大，已自動分成多張', COMPARISON_SPLIT:'對照內容太多，已自動分成多張',
    MISSING_IMAGE:'找不到要放進去的圖片', TEMPLATE_FALLBACK:'選的版型無法套用，改用預設版面', PROVENANCE_MISSING:'缺少資料來源的紀錄',
    NOTES_MISSING:'缺少講者備註', EMPTY_SLIDE:'有空白的投影片', NO_RENDERABLE_SLIDES:'沒有可以做成投影片的內容',
    OVERFLOW_RISK:'文字可能超出版面，請打開檢查', MANUAL_ARTIFACT_UNCHECKED:'這是手動上傳的檔案，系統沒有檢查過內容',
    AUTO_PICTURES:'系統自動配了圖片，請確認圖片合適'
  };
  function qualityLine(item) {
    const slide = /^s(\d+)$/i.exec(String(item.slideId || ''));
    const where = slide ? `第 ${slide[1]} 張：` : '';
    const detail = item.detail ? `（${item.detail}）` : '';
    return `・${where}${QUALITY_TEXT[item.code] || '需要人工確認'}${detail}`;
  }
  function qualityText(data) {
    const q = data?.quality || {}, errors = q.errors || [], warnings = q.warnings || [];
    const head = errors.length ? `❌ 有 ${errors.length} 個嚴重問題，修好之前無法發布` : warnings.length ? `⚠️ 有 ${warnings.length} 個提醒，發布前需要你確認` : '✅ 檢查通過，沒有發現問題';
    const lines = [head, q.slideCount ? `共 ${q.slideCount} 張投影片` : ''];
    if (errors.length) lines.push('', '【嚴重問題】', ...errors.map(qualityLine));
    if (warnings.length) lines.push('', '【提醒】', ...warnings.map(qualityLine));
    lines.push('', data?.publishable === false ? '目前不能發布。' : '可以發布。');
    return lines.filter((line, index) => line !== '' || index > 1).join('\n');
  }
  async function action(event) {
    const use = event.target.closest('[data-use-presentation]');
    if (use) {
      const id = String(use.dataset.usePresentation || '');
      const chosen = presentationRows.find(item => String(item.id || '') === id);
      if (!chosen) return;
      currentPresentation = chosen; currentPresentationId = id;
      renderCurrentPresentation();
      await loadPublicationMaterials().catch(() => {});
      note(`已切換到 V${Number(chosen.revisionNumber || 1)}；只有你明確切換後，歷史版本才會成為目前工作版本。`);
      return;
    }
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const node = button.closest('[data-presentation-id]'), id = node?.dataset.presentationId;
    if (!id || String(id) !== String(currentPresentationId || '')) return;
    try {
      const output = node.querySelector('[data-output]');
      if (button.dataset.action === 'quality') {
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/quality`);
        output.textContent = qualityText(data);
        output.classList.toggle('hidden');
        return;
      }
      if (button.dataset.action === 'provenance') {
        const data = await api(`/api/ai-presentations/${encodeURIComponent(id)}/provenance`);
        const trace=data.trace||{}, material=trace.sourceMaterial||{}, draft=trace.sourceDraft||{}, ai=trace.ai||{}, template=trace.template||{}, approval=trace.approval||{}, rag=trace.rag||{};
        const captured=Number(material.capturedVersion||0), current=Number(material.currentVersion||0);
        output.textContent = [`來源教材：${material.title||'（名稱不可用）'}`,`來源教材版本：${captured?'v'+captured:'舊版本未記錄'}${current?'｜目前 v'+current:''}${material.versionChanged?'｜⚠️ 來源教材之後已有新版':''}`,`來源投影片大綱：${draft.title||'（名稱不可用）'}｜${draft.status||'—'}`,`大綱核准：${approval.teacher||draft.approvedBy||'—'}｜${approval.at||draft.approvedAt||'—'}`,`RAG 來源片段：${Number(rag.chunkCount||0)} 個`,`AI：${ai.provider||'—'} / ${ai.model||'—'}`,`PowerPoint 範本：${template.name||'未套用範本'}`,`目前簡報 revision：r${Number(data.revisionNumber||1)}`].join('\n');
        output.classList.toggle('hidden');
        return;
      }
      if (button.dataset.action === 'discard') {
        if (!confirm('確定捨棄這份 PowerPoint 草稿嗎？檔案會立即刪除，無法復原。')) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}`, {method:'DELETE'});
        note('🗑 已捨棄這份 PowerPoint。');
        currentPresentationId = '';
        await loadPresentations();
        return;
      }
      if (button.dataset.action === 'approve') {
        if (!confirm('確認已檢查目前 PowerPoint revision 的內容與來源，並核准嗎？')) return;
        await api(`/api/ai-presentations/${encodeURIComponent(id)}/approve`, {method:'POST'});
        note('✅ 已核准目前 revision，可直接進行正式發布。');
        await loadPresentations();
        return;
      }
      if (button.dataset.action !== 'publish') return;
      const publicationMaterialId = $('teacher-ai-presentation-publication-material-1016')?.value || '';
      if (!publicationMaterialId) throw new Error('本次 PowerPoint 尚未建立正式教材；請按「建立本次正式教材」，不需要從舊教材中挑選。');
      const check = await api(`/api/ai-presentations/${encodeURIComponent(id)}/quality`);
      if (check.quality?.status === 'error') throw new Error('品質檢查有阻擋錯誤，請先修正或重新產生。');
      const acknowledgeWarnings = check.quality?.status === 'warning' && confirm('此版本有品質警告；確認已檢視並仍要發布嗎？');
      if (check.quality?.status === 'warning' && !acknowledgeWarnings) return;
      if (!confirm(`確認正式發布目前的 V${Number(currentPresentation?.revisionNumber || 1)} 嗎？系統不會改用其他舊版本。`)) return;
      const published = await api(`/api/ai-presentations/${encodeURIComponent(id)}/publish-link`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({publicationMaterialId, acknowledgeWarnings})});
      const materialVersion=Number(published.materialDerivative?.materialVersion||0);
      note(`✅ 已正式發布目前 PowerPoint V${Number(currentPresentation?.revisionNumber || 1)}${materialVersion?'，並記錄在教材 V'+materialVersion+' 的衍生內容歷程。':'。'}`);
      window.dispatchEvent(new CustomEvent('teacher-ai-presentation-published',{detail:{presentationId:id,materialId:publicationMaterialId,title:currentPresentation?.title||'AI 教學投影片'}}));
      await loadPresentations();
    } catch (e) { note(e.message, true); }
  }
  function install() {
    const stage = $('teacher-ai-material-presentation-stage-1014');
    if (!stage || $('teacher-ai-presentation-1016')) return false;
    const panel = document.createElement('section');
    panel.id = 'teacher-ai-presentation-1016';
    panel.className = 'space-y-4';
    panel.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-violet-700">AI 投影片</p><h4 class="text-xl font-black text-slate-950">🖥️ AI 投影片製作室</h4><p class="mt-1 text-sm text-slate-600">在這一頁依序完成：核准大綱 → 選版型 → 產生投影片 → 你檢查修改 → 發布。</p><p id="teacher-ai-presentation-flow-1016" class="mt-2 text-xs font-bold text-violet-800">正在確認投影片製作服務…</p></div><span id="teacher-ai-presentation-provider-1016" class="rounded-full bg-violet-50 px-3 py-1.5 text-[11px] font-bold text-violet-800">檢查服務中…</span></div>
      <div class="rounded-xl border border-violet-100 bg-violet-50/50 p-4 space-y-3"><div><b class="text-sm text-slate-900">第 4 步｜選擇投影片版型（可以不選）</b><select id="teacher-ai-presentation-template-1016" class="learning-input mt-2"><option>讀取中…</option></select></div><div><b class="text-sm text-slate-900">第 5 步｜建立投影片</b><p id="teacher-ai-presentation-draft-summary-1016" class="mt-1 text-sm text-slate-600">請在 Step 3 建立、儲存並核准投影片大綱。</p><div class="mt-3 flex flex-wrap gap-2"><button id="teacher-ai-presentation-generate-1016" type="button" class="rounded-xl bg-violet-700 px-5 py-2.5 text-sm font-black text-white disabled:opacity-40">建立投影片</button><button id="teacher-ai-presentation-refresh-1016" type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-sm font-black text-slate-700">重新讀取結果</button></div><div id="teacher-ai-presentation-status-1016" class="mt-2 text-sm font-bold text-slate-600">大綱核准後，按上面的「建立投影片」。</div></div></div>
      <div class="rounded-xl border border-violet-200 bg-violet-50/30 p-4 space-y-3"><div><b class="text-sm text-slate-900">第 6 步｜確認並發布這份投影片</b><p class="mt-1 text-xs text-slate-600">系統會直接使用你剛做好的這一版，不需要再從舊的投影片或教材清單裡重新挑選。</p></div><input id="teacher-ai-presentation-publication-material-1016" type="hidden" value=""><div id="teacher-ai-presentation-results-1016" class="space-y-2"></div><div id="teacher-ai-presentation-publication-target-1016"></div><button id="teacher-ai-presentation-create-material-1016" type="button" class="hidden rounded-xl border border-amber-200 bg-white px-3 py-2 text-xs font-black text-amber-800">建立本次正式教材</button></div>
      <details id="teacher-ai-presentation-history-1016" class="rounded-xl border border-slate-200 bg-slate-50/60 p-4"><summary class="cursor-pointer text-sm font-black text-slate-700">以前做過的版本／改用其他版本</summary><p class="mt-2 text-xs text-slate-500">只列出這份教材以前做過的版本，不會混入其他教材的投影片。</p><div id="teacher-ai-presentation-history-list-1016" class="mt-3 space-y-2"></div></details>
      <p class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] text-amber-900"><b>品質檢查：</b>有嚴重錯誤的投影片無法發布；有警告時，需要你確認後才能發布。系統會保留每個版本和資料來源的紀錄。</p>`;
    stage.replaceChildren(panel);
    panel.addEventListener('click', action);
    $('teacher-ai-presentation-generate-1016').addEventListener('click', generate);
    $('teacher-ai-presentation-refresh-1016').addEventListener('click', () => { currentPresentationId = ''; void loadPresentations({preferLatest:true}).catch(e => note(e.message, true)); });
    $('teacher-ai-presentation-create-material-1016').addEventListener('click', () => window.dispatchEvent(new CustomEvent('teacher-ai-material-request-publication')));
    void Promise.all([loadStatus(), loadTemplates(), loadPublicationMaterials()]).then(() => loadPresentations()).catch(e => note(e.message, true));
    return true;
  }
  window.addEventListener('teacher-ai-material-draft-selected', event => {
    const next = event.detail?.draft || null;
    if (String(next?.id || '') !== String(selectedDraft?.id || '')) currentPresentationId = '';
    selectedDraft = next;
    syncDraft();
    void loadPresentations({preferLatest:true}).catch(e => note(e.message, true));
  });
  window.addEventListener('teacher-ai-material-published', event => {
    if (selectedDraft) selectedDraft = {...selectedDraft, publicationMaterialId:String(event.detail?.materialId || '')};
    void loadPublicationMaterials(event.detail?.materialId || '').catch(e => note(e.message, true));
  });
  if (!install()) { const observer = new MutationObserver(() => { if (install()) observer.disconnect(); }); observer.observe(document.body, {childList:true, subtree:true}); }
})();
