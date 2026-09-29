/* Teacher content ownership + audience controls.
 * Ownership stays on the canonical group; this UI only edits who may see/use
 * that content. Server RBAC/scope remains authoritative.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const canMaterials = has('material.manage');
  const canQuestions = has('question.manage');
  if (!canMaterials && !canQuestions) return;

  const META = {
    group_only: {label:'本組限定', icon:'🔒', cls:'bg-slate-100 text-slate-700'},
    all_staff: {label:'全科共用', icon:'🌐', cls:'bg-emerald-100 text-emerald-800'},
    multi_group: {label:'指定組別', icon:'👥', cls:'bg-indigo-100 text-indigo-800'},
  };

  const groupCatalog = typeof GROUPS !== 'undefined' ? GROUPS : (window.GROUPS || {});
  const groupLabel = key => groupCatalog[key]?.label || groupCatalog[key]?.name || key || '未設定組別';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  function metaFor(item) {
    const key = META[item?.audienceScope] ? item.audienceScope : 'group_only';
    return META[key];
  }

  function audienceTitle(item) {
    const meta = metaFor(item);
    if (item?.audienceScope !== 'multi_group') return `${meta.icon} ${meta.label}`;
    const groups = Array.isArray(item?.audienceGroups) ? item.audienceGroups : [];
    return `${meta.icon} ${meta.label}${groups.length ? `：${groups.map(groupLabel).join('、')}` : ''}`;
  }

  function chooseAudience(item) {
    const owner = item?.ownerGroup || item?.group || 'grpBio';
    const current = item?.audienceScope || 'group_only';
    const answer = prompt(
      `內容歸屬：${groupLabel(owner)}（歸屬不會因分享而改變）\n\n` +
      `請設定可見／使用範圍：\n1 = 🔒 本組限定\n2 = 🌐 全科共用\n3 = 👥 指定其他組別\n\n目前：${audienceTitle(item)}`,
      current === 'all_staff' ? '2' : (current === 'multi_group' ? '3' : '1')
    );
    if (answer === null) return null;
    const trimmed = String(answer).trim();
    if (trimmed === '1') return {audienceScope:'group_only', audienceGroups:[]};
    if (trimmed === '2') return {audienceScope:'all_staff', audienceGroups:[]};
    if (trimmed !== '3') {
      alert('請輸入 1、2 或 3。');
      return null;
    }
    const choices = Object.entries(groupCatalog)
      .filter(([key]) => key !== owner)
      .map(([key]) => `${key}=${groupLabel(key)}`)
      .join('、');
    const previous = (Array.isArray(item?.audienceGroups) ? item.audienceGroups : []).join(',');
    const raw = prompt(`請輸入要分享的組別代碼，可用逗號分隔：\n${choices}`, previous);
    if (raw === null) return null;
    const groups = [...new Set(String(raw).split(',').map(x=>x.trim()).filter(key=>key && key !== owner && groupCatalog[key]))];
    if (!groups.length) {
      alert('指定組別至少要選擇一個其他組別。');
      return null;
    }
    return {audienceScope:'multi_group', audienceGroups:groups};
  }

  async function patchAudience(kind, id, item) {
    const payload = chooseAudience(item);
    if (!payload) return null;
    const response = await fetch(`/api/content-audience/${kind}/${encodeURIComponent(id)}`, {
      method:'PATCH',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '可見範圍更新失敗');
    return data;
  }

  function audienceControl(item, onClick) {
    const meta = metaFor(item);
    const host = document.createElement('span');
    host.className = 'inline-flex items-center gap-1.5';
    const badge = document.createElement('span');
    badge.className = `text-[10px] px-2 py-0.5 rounded-full font-bold ${meta.cls}`;
    badge.textContent = audienceTitle(item);
    badge.title = `內容所有者：${groupLabel(item?.ownerGroup || item?.group || '')}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'text-[10px] rounded-lg border border-slate-200 bg-white px-2 py-1 font-bold text-slate-600 hover:bg-slate-50';
    button.textContent = '設定範圍';
    button.addEventListener('click', onClick);
    host.append(badge, button);
    return host;
  }

  async function editMaterialAudience(id, item) {
    try {
      const data = await patchAudience('materials', id, item);
      if (!data) return;
      window.invalidateAdminMaterialsCache?.();
      await window.renderAdminMaterials?.(true);
      await window.renderAdminCourseMaterialHub?.(true);
    } catch (error) {
      alert(error.message);
    }
  }

  function decorateMaterials() {
    if (!canMaterials) return;
    const box = document.getElementById('admin-materials-list');
    if (!box) return;
    const materials = Array.isArray(adminMaterialsCache?.data) ? adminMaterialsCache.data : [];
    materials.filter(item=>!item.isBuiltin).forEach(item => {
      const button = [...box.querySelectorAll('[data-csp-click]')].find(node =>
        String(node.getAttribute('data-csp-click') || '').includes(`editAdminMaterial('${item.id}')`)
      );
      const row = button?.closest('.border.border-slate-200');
      if (!row || row.querySelector(`[data-content-audience-material="${CSS.escape(String(item.id))}"]`)) return;
      const firstInfo = row.querySelector('.flex.items-center.gap-2.flex-wrap');
      if (!firstInfo) return;
      const host = audienceControl(item, () => editMaterialAudience(item.id, item));
      host.dataset.contentAudienceMaterial = String(item.id);
      firstInfo.appendChild(host);
    });
  }

  async function editQuestionAudience(qId, catId, item) {
    try {
      const data = await patchAudience('questions', qId, item);
      if (!data) return;
      await window.loadQuizQuestionsIntoPanel?.(catId);
    } catch (error) {
      alert(error.message);
    }
  }

  function ensureSharedQuestionButton(catId) {
    if (!canQuestions) return;
    const panel = document.getElementById(`qpanel-${catId}`);
    if (!panel || panel.querySelector('[data-content-audience-shared-import]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.contentAudienceSharedImport = catId;
    button.className = 'mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] font-black text-emerald-800';
    button.textContent = '🌐 從跨組共用題庫匯入';
    button.addEventListener('click', () => importSharedQuestion(catId));
    panel.prepend(button);
  }

  function decorateQuestions(catId) {
    if (!canQuestions) return;
    const list = (typeof adminQuizQuestionCache !== 'undefined' && Array.isArray(adminQuizQuestionCache[catId]))
      ? adminQuizQuestionCache[catId]
      : [];
    list.forEach(item => {
      const row = document.getElementById(`qrow-${item.id}`);
      if (!row || row.querySelector('[data-content-audience-question]')) return;
      const info = row.querySelector('.flex.items-center.gap-2.flex-wrap');
      if (!info) return;
      const host = audienceControl(item, () => editQuestionAudience(item.id, catId, item));
      host.dataset.contentAudienceQuestion = String(item.id);
      info.appendChild(host);
    });
    ensureSharedQuestionButton(catId);
  }

  async function importSharedQuestion(catId) {
    const targetGroup = document.getElementById('admin-quiz-group')?.value || window.currentGroupKey || '';
    if (!targetGroup) return alert('無法確認目標組別。');
    try {
      const response = await fetch(`/api/content-audience/questions/shared?targetGroup=${encodeURIComponent(targetGroup)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const rows = await response.json().catch(() => []);
      if (!response.ok) throw new Error(rows.error || '共用題庫讀取失敗');
      const shared = (Array.isArray(rows) ? rows : []).filter(item => item.ownerGroup !== targetGroup);
      if (!shared.length) return alert('目前沒有其他組分享給此組使用的題目。');
      const shown = shared.slice(0, 30);
      const menu = shown.map((item, index) =>
        `${index + 1}. [${groupLabel(item.ownerGroup)}｜${item.audienceLabel || metaFor(item).label}] ${String(item.question || '').replace(/\s+/g,' ').slice(0, 80)}`
      ).join('\n');
      const answer = prompt(`選擇要複製到目前考卷的共用題目（輸入 1-${shown.length}）：\n\n${menu}`, '1');
      if (answer === null) return;
      const index = Number.parseInt(answer, 10) - 1;
      if (!Number.isInteger(index) || index < 0 || index >= shown.length) return alert('題目編號不正確。');
      const source = shown[index];
      if (!confirm(`從「${groupLabel(source.ownerGroup)}」共用題庫複製這題到目前考卷？\n\n原題仍由來源組管理，你這裡會建立獨立副本。`)) return;
      const copy = await fetch(`/api/content-audience/questions/${encodeURIComponent(source.id)}/copy`, {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({targetCategoryId:catId}),
      });
      const result = await copy.json().catch(() => ({}));
      if (!copy.ok) throw new Error(result.error || '題目匯入失敗');
      await window.loadQuizQuestionsIntoPanel?.(catId);
      alert('✅ 已建立獨立題目副本；來源組原題不會被修改。');
    } catch (error) {
      alert(error.message);
    }
  }

  function ensureUploadNotice() {
    if (!canMaterials || document.getElementById('content-audience-upload-notice-1014')) return;
    const title = document.getElementById('admin-material-title');
    const host = title?.closest('section,div');
    if (!title || !host) return;
    const notice = document.createElement('div');
    notice.id = 'content-audience-upload-notice-1014';
    notice.className = 'mt-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] leading-5 text-slate-600';
    notice.innerHTML = '<b>🔒 新教材預設本組限定。</b> 教材建立完成後可在教材清單直接改成「🌐 全科共用」或「👥 指定組別」；教材歸屬組別不會因此改變。';
    host.appendChild(notice);
  }

  const originalRenderMaterials = window.renderAdminMaterials;
  if (typeof originalRenderMaterials === 'function') {
    window.renderAdminMaterials = async function (...args) {
      const result = await originalRenderMaterials.apply(this, args);
      decorateMaterials();
      ensureUploadNotice();
      return result;
    };
  }

  const originalRenderQuestions = window.renderFilteredQuestionList;
  if (typeof originalRenderQuestions === 'function') {
    window.renderFilteredQuestionList = function (catId, ...args) {
      const result = originalRenderQuestions.call(this, catId, ...args);
      decorateQuestions(catId);
      return result;
    };
  }

  const originalLoadQuestions = window.loadQuizQuestionsIntoPanel;
  if (typeof originalLoadQuestions === 'function') {
    window.loadQuizQuestionsIntoPanel = async function (catId, ...args) {
      const result = await originalLoadQuestions.call(this, catId, ...args);
      decorateQuestions(catId);
      return result;
    };
  }

  ensureUploadNotice();
  decorateMaterials();
  window.ContentAudience1014 = Object.freeze({
    decorateMaterials,
    decorateQuestions,
    importSharedQuestion,
  });
})();
