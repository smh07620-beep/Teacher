/* Teacher AI subtitles: Worker transcription -> teacher review -> approved WebVTT playback. */
(async function () {
  'use strict';

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));

  async function approvedSubtitle(materialId) {
    if (!materialId) return null;
    try {
      const response = await fetch(`/api/materials/${encodeURIComponent(materialId)}/subtitles/approved`, {
        credentials:'same-origin', cache:'no-store'
      });
      if (!response.ok) return null;
      const data = await response.json().catch(() => ({}));
      return data.subtitle || null;
    } catch (_) {
      return null;
    }
  }

  async function attachApprovedTrack(materialId) {
    const video = document.getElementById('media-video');
    if (!video) return;
    video.querySelectorAll('track[data-teacher-ai-subtitle="1"]').forEach(track => track.remove());
    const subtitle = await approvedSubtitle(materialId);
    if (!subtitle?.vttUrl) return;
    const track = document.createElement('track');
    track.kind = 'subtitles';
    track.srclang = subtitle.language || 'zh-TW';
    track.label = subtitle.label || 'AI 字幕';
    track.src = subtitle.vttUrl;
    track.default = true;
    track.dataset.teacherAiSubtitle = '1';
    video.appendChild(track);
  }

  function installPlayerHook() {
    if (window.__teacherAiSubtitlePlayerInstalled) return true;
    if (typeof window.openMaterial !== 'function') return false;
    const originalOpen = window.openMaterial;
    window.openMaterial = async function (materialId) {
      const result = await originalOpen.apply(this, arguments);
      void attachApprovedTrack(materialId);
      return result;
    };
    window.__teacherAiSubtitlePlayerInstalled = true;
    return true;
  }
  if (!installPlayerHook()) {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (installPlayerHook() || attempts > 40) clearInterval(timer);
    }, 250);
  }

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  let subtitles = [];
  let activeJob = '';
  let pollToken = 0;

  const sourceMaterialId = () => document.getElementById('teacher-script-material-1014')?.value || '';
  const sourceLabel = () => document.getElementById('teacher-script-material-1014')?.selectedOptions?.[0]?.textContent || '';

  function setStatus(message, tone = 'normal') {
    const node = document.getElementById('teacher-subtitle-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-xs font-bold text-rose-700'
      : tone === 'success'
        ? 'text-xs font-bold text-emerald-700'
        : 'text-xs text-slate-600';
  }

  function setBusy(busy) {
    ['teacher-subtitle-generate-1014','teacher-subtitle-save-1014','teacher-subtitle-approve-1014'].forEach(id => {
      const node = document.getElementById(id);
      if (node) node.disabled = busy;
    });
  }

  function selectedSubtitle() {
    const id = document.getElementById('teacher-subtitle-draft-1014')?.value || '';
    return subtitles.find(item => item.id === id) || null;
  }

  function renderSelected() {
    const subtitle = selectedSubtitle();
    const editor = document.getElementById('teacher-subtitle-vtt-1014');
    const meta = document.getElementById('teacher-subtitle-meta-1014');
    const approve = document.getElementById('teacher-subtitle-approve-1014');
    const srt = document.getElementById('teacher-subtitle-srt-1014');
    if (!editor || !meta || !approve || !srt) return;
    if (!subtitle) {
      editor.value = '';
      editor.disabled = true;
      approve.disabled = true;
      srt.classList.add('hidden');
      meta.textContent = '尚未選擇字幕草稿。';
      return;
    }
    editor.disabled = false;
    editor.value = subtitle.vttText || '';
    approve.disabled = false;
    const fallback = subtitle.fallbackUsed ? '｜已使用備援' : '';
    meta.textContent = `${subtitle.status === 'approved' ? '✅ 已核准' : '📝 待教師確認'}｜${subtitle.provider || 'AI'} / ${subtitle.model || ''}${fallback}｜來源 V${subtitle.sourceVersion || 1}`;
    srt.href = `/api/media-subtitles/${encodeURIComponent(subtitle.id)}.srt`;
    srt.classList.toggle('hidden', subtitle.status !== 'approved');
  }

  async function loadSubtitles() {
    const select = document.getElementById('teacher-subtitle-draft-1014');
    if (!select) return;
    const materialId = sourceMaterialId();
    subtitles = [];
    select.innerHTML = '<option value="">請先選擇影音教材</option>';
    renderSelected();
    if (!materialId) {
      setStatus('請先在上方選擇來源影音教材。');
      return;
    }
    try {
      const response = await fetch(`/api/media-subtitles?materialId=${encodeURIComponent(materialId)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const data = await response.json().catch(() => ([]));
      if (!response.ok) throw new Error(data.error || '無法讀取字幕草稿');
      subtitles = Array.isArray(data) ? data : [];
      select.innerHTML = '<option value="">選擇字幕草稿…</option>';
      subtitles.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id || '';
        option.textContent = `${item.status === 'approved' ? '✅' : '📝'} ${item.label || '字幕'}｜${item.provider || 'AI'}｜V${item.sourceVersion || 1}`;
        select.appendChild(option);
      });
      if (subtitles.length) {
        select.value = subtitles[0].id || '';
        setStatus(`已找到 ${subtitles.length} 份字幕紀錄；請確認時間軸與文字後再核准。`, 'success');
      } else {
        setStatus('目前尚無字幕，可使用 AI 產生草稿。');
      }
      renderSelected();
    } catch (error) {
      select.innerHTML = '<option value="">字幕讀取失敗</option>';
      setStatus(`字幕讀取失敗：${error.message}`, 'error');
    }
  }

  async function pollJob(jobId, token) {
    while (token === pollToken && activeJob === jobId) {
      const response = await fetch(`/api/media-subtitles/jobs/${encodeURIComponent(jobId)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取 AI 字幕工作進度');
      const progress = data.progress || {};
      setStatus(`${progress.stage || 'AI 字幕處理中'}｜${Math.round(Number(progress.percent || 0))}%${progress.detail ? `｜${progress.detail}` : ''}`);
      if (data.status === 'completed') {
        setBusy(false);
        await loadSubtitles();
        setStatus('✅ AI 字幕草稿已完成；請人工確認後按「教師核准字幕」。', 'success');
        return;
      }
      if (data.status === 'failed') {
        setBusy(false);
        throw new Error(data.error || 'AI 字幕產生失敗');
      }
      await new Promise(resolve => setTimeout(resolve, 1800));
    }
  }

  async function generate() {
    const materialId = sourceMaterialId();
    if (!materialId) return setStatus('請先選擇來源影音教材。', 'error');
    if (!confirm(`確定要為「${sourceLabel() || '這份影音教材'}」產生 AI 字幕草稿嗎？\n\n字幕不會自動發布，完成後仍需教師確認與核准。`)) return;
    setBusy(true);
    setStatus('正在建立 AI 字幕工作…');
    try {
      const response = await fetch('/api/media-subtitles/generate', {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          materialId,
          language: document.getElementById('teacher-subtitle-language-1014')?.value || 'zh-TW',
          label: document.getElementById('teacher-subtitle-label-1014')?.value || '繁體中文字幕',
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法建立 AI 字幕工作');
      activeJob = data.jobId || '';
      if (!activeJob) throw new Error('伺服器沒有回傳 AI 字幕工作 ID');
      await pollJob(activeJob, ++pollToken);
    } catch (error) {
      setBusy(false);
      setStatus(`AI 字幕產生失敗：${error.message}`, 'error');
    }
  }

  async function save(status) {
    const subtitle = selectedSubtitle();
    if (!subtitle) return setStatus('請先選擇字幕草稿。', 'error');
    const vttText = document.getElementById('teacher-subtitle-vtt-1014')?.value || '';
    const label = document.getElementById('teacher-subtitle-label-1014')?.value || subtitle.label || '繁體中文字幕';
    if (status === 'approved' && !confirm('確定核准這份字幕嗎？核准後學員播放此版本影音時會自動載入字幕。')) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/media-subtitles/${encodeURIComponent(subtitle.id)}`, {
        method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({vttText, label, status}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '字幕更新失敗');
      await loadSubtitles();
      setStatus(status === 'approved' ? '✅ 字幕已由教師核准並可供學員播放器使用。' : '字幕草稿已儲存。', 'success');
    } catch (error) {
      setStatus(`字幕更新失敗：${error.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  function installAdmin() {
    const media = document.getElementById('teacher-media-production-1014');
    const source = document.getElementById('teacher-script-material-1014');
    if (!media || !source || document.getElementById('teacher-media-subtitle-1014')) return false;
    const section = document.createElement('section');
    section.id = 'teacher-media-subtitle-1014';
    section.className = 'bg-white border border-cyan-200 rounded-2xl p-5 shadow-sm space-y-4';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div><p class="admin-page-eyebrow text-cyan-700">AI CAPTIONS</p><h4 class="text-lg font-black text-slate-950">💬 影音 → AI 字幕（教師核准後發布）</h4><p class="mt-1 text-xs text-slate-500">上傳影音與允許的 hospital CDN direct video 可由 AI Worker 轉錄成 WebVTT/SRT。YouTube/Vimeo 不下載原始影音，僅使用平台本身提供的字幕。</p></div>
        <span class="rounded-full bg-cyan-50 px-3 py-1.5 text-[11px] font-bold text-cyan-800">本機 Whisper 優先符合院方隱私設定</span>
      </div>
      <div class="grid md:grid-cols-3 gap-3">
        <label class="text-xs font-bold text-slate-600">語言代碼<input id="teacher-subtitle-language-1014" value="zh-TW" maxlength="32" class="learning-input mt-1"></label>
        <label class="text-xs font-bold text-slate-600 md:col-span-2">字幕名稱<input id="teacher-subtitle-label-1014" value="繁體中文字幕" maxlength="80" class="learning-input mt-1"></label>
      </div>
      <div class="flex flex-col sm:flex-row sm:items-center gap-3"><button id="teacher-subtitle-generate-1014" type="button" class="rounded-xl bg-cyan-700 px-5 py-2.5 text-xs font-black text-white">💬 產生 AI 字幕草稿</button><span id="teacher-subtitle-status-1014" class="text-xs text-slate-600">選擇影音教材後即可開始。</span></div>
      <label class="block text-xs font-bold text-slate-600">字幕版本<select id="teacher-subtitle-draft-1014" class="learning-input mt-1"><option value="">請先選擇影音教材</option></select></label>
      <div id="teacher-subtitle-meta-1014" class="text-[11px] text-slate-500">尚未選擇字幕草稿。</div>
      <label class="block text-xs font-bold text-slate-600">WebVTT 字幕內容<textarea id="teacher-subtitle-vtt-1014" disabled rows="14" spellcheck="false" class="learning-input mt-1 font-mono text-[11px]" placeholder="WEBVTT"></textarea></label>
      <div class="flex flex-wrap items-center gap-2"><button id="teacher-subtitle-save-1014" type="button" class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-black text-slate-700">儲存草稿</button><button id="teacher-subtitle-approve-1014" type="button" class="rounded-xl bg-emerald-700 px-4 py-2 text-xs font-black text-white">✅ 教師核准字幕</button><a id="teacher-subtitle-srt-1014" class="hidden rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-2 text-xs font-black text-cyan-800" href="#">下載 SRT</a></div>
      <div class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] leading-5 text-amber-900"><b>安全規則：</b>AI 只產生草稿；教材更新版本後舊字幕不會繼續發布。當 AI_EXTERNAL_MEDIA_ALLOWED=false 時，影音不送外部 AI，改由本機 faster-whisper 轉錄。</div>`;
    const audio = document.getElementById('teacher-media-audio-1014');
    if (audio) audio.insertAdjacentElement('afterend', section); else media.appendChild(section);
    source.addEventListener('change', () => void loadSubtitles());
    document.getElementById('teacher-subtitle-draft-1014')?.addEventListener('change', renderSelected);
    document.getElementById('teacher-subtitle-generate-1014')?.addEventListener('click', () => void generate());
    document.getElementById('teacher-subtitle-save-1014')?.addEventListener('click', () => void save('draft'));
    document.getElementById('teacher-subtitle-approve-1014')?.addEventListener('click', () => void save('approved'));
    void loadSubtitles();
    return true;
  }

  if (!installAdmin()) {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (installAdmin() || attempts > 40) clearInterval(timer);
    }, 250);
  }
})();
