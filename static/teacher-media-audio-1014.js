/* Teacher 10/14 media MVP: approved teacher script -> AI narration -> R2 material. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  let activeJobId = '';
  let pollToken = 0;
  let statusInfo = null;
  let scripts = [];

  const voiceLabel = value => ({
    zf_xiaoxiao: '曉曉｜女聲', zf_xiaobei: '小北｜女聲', zf_xiaoni: '小妮｜女聲',
    zf_xiaoyi: '小藝｜女聲', zm_yunxi: '雲希｜男聲', zm_yunjian: '雲健｜男聲',
    zm_yunxia: '雲夏｜男聲', zm_yunyang: '雲揚｜男聲'
  }[String(value || '')] || '中文教學聲音');

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));

  function setStatus(message, tone = 'normal') {
    const node = document.getElementById('teacher-audio-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-xs font-bold text-rose-700'
      : tone === 'success'
        ? 'text-xs font-bold text-emerald-700'
        : 'text-xs text-slate-600';
  }

  function setBusy(busy) {
    const button = document.getElementById('teacher-audio-generate-1014');
    const script = document.getElementById('teacher-audio-script-1014');
    const voice = document.getElementById('teacher-audio-voice-1014');
    if (button) button.disabled = busy || !statusInfo?.enabled;
    if (script) script.disabled = busy;
    if (voice) voice.disabled = busy;
  }

  function sourceMaterialId() {
    return document.getElementById('teacher-script-material-1014')?.value || '';
  }

  function sourceMaterialLabel() {
    const select = document.getElementById('teacher-script-material-1014');
    return select?.selectedOptions?.[0]?.textContent || '';
  }

  async function loadStatus() {
    try {
      const response = await fetch('/api/media-audio/status', {credentials:'same-origin', cache:'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取 AI 語音狀態');
      statusInfo = data || {};
      const voice = document.getElementById('teacher-audio-voice-1014');
      if (voice) {
        voice.replaceChildren();
        (Array.isArray(data.voices) ? data.voices : []).forEach(item => {
          const option = document.createElement('option');
          option.value = item;
          option.textContent = voiceLabel(item);
          if (item === data.defaultVoice) option.selected = true;
          voice.appendChild(option);
        });
      }
      const disclosure = document.getElementById('teacher-audio-disclosure-1014');
      if (disclosure) disclosure.textContent = data.disclosure || '本音訊為 AI 合成語音。';
      const provider = document.getElementById('teacher-audio-provider-1014');
      if (provider) provider.textContent = data.enabled
        ? '本機 AI｜隱私模式｜媒體安全保存'
        : 'AI 語音服務尚未啟用';
      setBusy(false);
      if (!data.enabled) setStatus('AI 語音尚未啟用；老師錄音／錄影功能仍可正常使用。', 'error');
      return data;
    } catch (error) {
      statusInfo = {enabled:false};
      setBusy(false);
      setStatus(`AI 語音狀態讀取失敗：${error.message}`, 'error');
      return statusInfo;
    }
  }

  async function loadApprovedScripts() {
    const select = document.getElementById('teacher-audio-script-1014');
    if (!select) return;
    const previous = select.value;
    select.innerHTML = '<option value="">讀取已核准講稿…</option>';
    const materialId = sourceMaterialId();
    if (!materialId) {
      scripts = [];
      select.innerHTML = '<option value="">請先在上方選擇來源教材</option>';
      setStatus('先選擇教材並完成「教師核准講稿」，才能產生 AI 語音。');
      return;
    }
    try {
      const response = await fetch(`/api/media-scripts?materialId=${encodeURIComponent(materialId)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const data = await response.json().catch(() => []);
      if (!response.ok) throw new Error(data.error || '無法讀取講稿');
      scripts = (Array.isArray(data) ? data : []).filter(item => item.status === 'approved');
      select.innerHTML = '<option value="">選擇已核准講稿…</option>';
      scripts.forEach(script => {
        const option = document.createElement('option');
        option.value = script.id || '';
        option.textContent = `${script.title || '教學講稿'}${script.approvedBy ? `｜核准：${script.approvedBy}` : ''}`;
        select.appendChild(option);
      });
      if (!scripts.length) {
        select.innerHTML = '<option value="">這份教材尚無已核准講稿</option>';
        setStatus('這份教材目前沒有已核准講稿；請先完成講稿編修與教師核准。');
      } else {
        if (scripts.some(script => script.id === previous)) select.value = previous;
        else if (scripts.length === 1) select.value = scripts[0].id || '';
        setStatus(`已找到 ${scripts.length} 份已核准講稿，可選擇後產生 AI 語音。`, 'success');
      }
    } catch (error) {
      scripts = [];
      select.innerHTML = '<option value="">讀取講稿失敗</option>';
      setStatus(`講稿讀取失敗：${error.message}`, 'error');
    }
  }

  function showResult(data) {
    const host = document.getElementById('teacher-audio-result-1014');
    if (!host) return;
    const result = data?.result || {};
    const material = result.material || {};
    host.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div><b class="text-sm text-emerald-950">✅ AI 語音教材已建立</b>
        <p class="mt-1 text-xs text-slate-700">${escapeHtml(material.title || material.filename || result.materialId || '')}</p>
        <p class="mt-1 text-[11px] text-slate-500">已使用 ${escapeHtml(voiceLabel(result.voice))} 產生 AI 語音。</p></div>
        <button id="teacher-audio-back-course-1014" type="button" class="rounded-xl border border-emerald-200 bg-white px-3 py-2 text-xs font-black text-emerald-700">回教材與課程查看</button>
      </div>
      <div class="mt-3 rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] text-amber-900">${escapeHtml(result.disclosure || statusInfo?.disclosure || '本音訊為 AI 合成語音。')}</div>`;
    host.classList.remove('hidden');
    host.querySelector('#teacher-audio-back-course-1014')?.addEventListener('click', async () => {
      window.invalidateAdminMaterialsCache?.();
      await window.TeacherWorkspace1014?.openCourse?.();
      void window.renderAdminCourseMaterialHub?.(true);
    });
  }

  async function pollJob(jobId, token) {
    while (token === pollToken && activeJobId === jobId) {
      const response = await fetch(`/api/media-audio/jobs/${encodeURIComponent(jobId)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取 AI 語音工作進度');
      const progress = data.progress || {};
      setStatus(`${progress.stage || 'AI 語音處理中'}｜${Math.round(Number(progress.percent || 0))}%${progress.detail ? `｜${progress.detail}` : ''}`);
      if (data.status === 'completed') {
        setBusy(false);
        showResult(data);
        window.invalidateAdminMaterialsCache?.();
        void window.renderAdminCourseMaterialHub?.(true);
        void window.renderSlidesGrid?.();
        setStatus('✅ AI 語音完成，已直接保存至 R2 並加入教材；教材清單已同步更新。', 'success');
        return;
      }
      if (data.status === 'failed') {
        setBusy(false);
        throw new Error(data.error || 'AI 語音產生失敗');
      }
      await new Promise(resolve => setTimeout(resolve, 1800));
    }
  }

  async function generateAudio() {
    const scriptId = document.getElementById('teacher-audio-script-1014')?.value || '';
    if (!scriptId) {
      setStatus('請選擇一份已核准講稿。', 'error');
      return;
    }
    if (!statusInfo?.enabled) {
      setStatus('AI 語音尚未啟用；請由系統管理者完成 OPENAI_API_KEY 與 R2 設定。', 'error');
      return;
    }
    const script = scripts.find(item => item.id === scriptId);
    if (!script || script.status !== 'approved') {
      setStatus('只能使用目前仍為「已核准」狀態的講稿。', 'error');
      return;
    }
    if (!confirm(`確定使用已核准講稿「${script.title || '教學講稿'}」產生 AI 語音嗎？\n\n來源教材：${sourceMaterialLabel()}\n產生後會直接保存至 R2 並加入原課程教材。`)) return;

    const payload = {
      scriptId,
      voice: document.getElementById('teacher-audio-voice-1014')?.value || statusInfo.defaultVoice || '',
      instructions: String(document.getElementById('teacher-audio-instructions-1014')?.value || '').trim(),
    };
    setBusy(true);
    document.getElementById('teacher-audio-result-1014')?.classList.add('hidden');
    setStatus('正在建立 AI 語音工作…');
    try {
      const response = await fetch('/api/media-audio/generate', {
        method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法建立 AI 語音工作');
      activeJobId = data.jobId || '';
      if (!activeJobId) throw new Error('伺服器沒有回傳 AI 語音工作 ID');
      const token = ++pollToken;
      await pollJob(activeJobId, token);
    } catch (error) {
      setBusy(false);
      setStatus(`AI 語音產生失敗：${error.message}`, 'error');
    }
  }

  async function previewVoice() {
    const voice = document.getElementById('teacher-audio-voice-1014')?.value || statusInfo?.defaultVoice || '';
    if (!voice || !statusInfo?.enabled) return setStatus('AI 語音尚未啟用，暫時無法試聽。', 'error');
    const button = document.getElementById('teacher-audio-preview-1018');
    if (button) button.disabled = true;
    setStatus('正在準備語音試聽…');
    try {
      const response = await fetch('/api/media-audio/preview', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({voice})});
      const job = await response.json().catch(() => ({}));
      if (!response.ok || !job.jobId) throw new Error(job.error || '無法建立語音試聽');
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const statusResponse = await fetch(`/api/media-audio/jobs/${encodeURIComponent(job.jobId)}`, {credentials:'same-origin', cache:'no-store'});
        const status = await statusResponse.json().catch(() => ({}));
        if (!statusResponse.ok) throw new Error(status.error || '無法讀取語音試聽進度');
        if (status.status === 'completed') {
          const url = status.result?.previewUrl;
          if (!url) throw new Error('語音試聽已完成，但暫時沒有可播放檔案');
          window.open(url, '_blank', 'noopener');
          setStatus('已開啟語音試聽。', 'success');
          return;
        }
        if (status.status === 'failed') throw new Error(status.error || '語音試聽失敗');
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
      throw new Error('語音試聽仍在處理，可稍後再試。');
    } catch (error) {
      setStatus(`語音試聽失敗：${error.message}`, 'error');
    } finally {
      if (button) button.disabled = false;
    }
  }

  function markCardReady() {
    document.querySelectorAll('#teacher-media-production-1014 article').forEach(card => {
      const heading = card.querySelector('h5')?.textContent || '';
      if (!heading.includes('AI 語音')) return;
      const badge = card.querySelector('span');
      if (!badge) return;
      badge.textContent = 'AI 語音可使用';
      badge.className = 'mt-3 inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-800';
    });
  }

  function install() {
    const media = document.getElementById('teacher-media-production-1014');
    if (!media || document.getElementById('teacher-media-audio-1014')) return false;
    const section = document.createElement('section');
    section.id = 'teacher-media-audio-1014';
    section.className = 'bg-white border border-emerald-200 rounded-2xl p-5 shadow-sm space-y-5';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div><p class="admin-page-eyebrow text-emerald-700">AI NARRATION</p><h4 class="text-lg font-black text-slate-950">🎧 已核准講稿 → AI 語音</h4><p class="mt-1 text-xs text-slate-500">只有授課教師已核准的講稿才能送出。語音由 AI Worker 產生，完成後直接保存至 R2 並加入原課程教材，不讓 Render Web 處理大型媒體工作。</p></div>
        <span id="teacher-audio-provider-1014" class="rounded-full bg-slate-100 px-3 py-1.5 text-[11px] font-bold text-slate-600">檢查服務中…</span>
      </div>
      <div class="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
        <label class="text-xs font-bold text-slate-600 xl:col-span-2">已核准講稿<select id="teacher-audio-script-1014" class="learning-input mt-1"><option value="">請先選擇來源教材</option></select></label>
        <label class="text-xs font-bold text-slate-600">AI 聲音<select id="teacher-audio-voice-1014" class="learning-input mt-1"><option value="">讀取中…</option></select></label>
      </div>
      <label class="block text-xs font-bold text-slate-600">語音風格指示（選填）<input id="teacher-audio-instructions-1014" maxlength="500" class="learning-input mt-1" placeholder="例如：清楚、沉穩、繁體中文教學語氣；醫療數值與縮寫照稿件念"></label>
      <div class="flex flex-col sm:flex-row sm:items-center gap-3"><button id="teacher-audio-generate-1014" type="button" disabled class="rounded-xl bg-emerald-700 px-5 py-2.5 text-xs font-black text-white disabled:opacity-40">🎙️ 產生 AI 語音</button><button id="teacher-audio-preview-1018" type="button" class="rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-xs font-black text-emerald-700">▶ 試聽</button><span id="teacher-audio-status-1014" class="text-xs text-slate-600">檢查 AI 語音服務中…</span></div>
      <div id="teacher-audio-result-1014" class="hidden rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4"></div>
      <div class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] leading-5 text-amber-900"><b>AI 語音揭露：</b><span id="teacher-audio-disclosure-1014">本音訊為 AI 合成語音。</span><br>正式內容仍以老師已核准講稿為準；講稿一旦修改即回到草稿狀態，需重新核准後才能再次產生語音。</div>`;

    const scriptStudio = document.getElementById('teacher-media-script-1014');
    if (scriptStudio?.nextSibling) media.insertBefore(section, scriptStudio.nextSibling);
    else media.prepend(section);

    document.getElementById('teacher-audio-generate-1014')?.addEventListener('click', generateAudio);
    document.getElementById('teacher-audio-preview-1018')?.addEventListener('click', () => void previewVoice());
    document.getElementById('teacher-script-material-1014')?.addEventListener('change', () => {
      activeJobId = '';
      pollToken += 1;
      void loadApprovedScripts();
    });
    markCardReady();
    void Promise.all([loadStatus(), loadApprovedScripts()]);
    return true;
  }

  if (!install()) {
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.TeacherMediaAudio1014 = Object.freeze({loadApprovedScripts, generateAudio, previewVoice});
})();
