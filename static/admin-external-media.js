/* Phase 3P · Canonical admin external interactive media runtime. */
(function(){
  'use strict';

  function safeEscape(value){
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(value);
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  window.openExternalMaterialLinkDrawer = async function(){
    const drawer = document.getElementById('external-material-drawer');
    const select = document.getElementById('external-material-id');
    drawer?.classList.remove('hidden');
    if (!select) return;

    select.innerHTML = '<option>載入教材…</option>';
    try {
      const loadMaterials = window.fetchAdminMaterials;
      if (typeof loadMaterials !== 'function') throw new Error('教材清單功能尚未載入');
      const rows = await loadMaterials(false);
      select.innerHTML = (rows || [])
        .filter(m => !m.isBuiltin)
        .map(m => `<option value="${safeEscape(m.id)}">${safeEscape(m.title || m.filename)}</option>`)
        .join('') || '<option value="">沒有可設定的教材</option>';
    } catch (_err) {
      select.innerHTML = '<option value="">教材載入失敗</option>';
    }
  };

  window.closeExternalMaterialLinkDrawer = function(){
    document.getElementById('external-material-drawer')?.classList.add('hidden');
  };

  window.saveExternalMaterialLinkToExisting = async function(){
    const id = document.getElementById('external-material-id')?.value;
    const url = document.getElementById('external-material-url')?.value.trim();
    const preview = document.getElementById('external-material-preview');
    if (!id || !url) return;
    try {
      const client = window.ExternalMediaClient;
      if (!client?.link) throw new Error('外部影音模組尚未載入');
      const data = await client.link(id, url);
      if (preview) preview.textContent = `✅ ${data.provider} · ${data.canonicalUrl}${data.videoId ? ' · ' + data.videoId : ''}`;
    } catch (error) {
      if (preview) preview.textContent = '❌ ' + (error.message || '網址驗證失敗');
    }
  };
})();
