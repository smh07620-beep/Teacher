/* AI VIDEO · PHASE 6 renderer contract; product surface is converged into F5. */
/* Teacher video Phase 6 workspace: approved PPT -> resilient renderer -> MP4 -> teacher review/publish. */
(async function () {
  'use strict';
  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  if (!['clinical_teacher','group_leader','education_admin','system_admin'].some(role => roles.has(role))) return;

  let active = '', poll = 0, status = {}, audioStatus = {};
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const rendererLabel = value => ({'powerpoint-com':'Microsoft PowerPoint','libreoffice-headless':'LibreOffice','text-fallback':'安全文字備援'}[String(value || '')] || String(value || '尚未記錄'));
  const qualityLabel = value => ({ok:'品質通過',warning:'品質警告',error:'品質阻擋'}[String(value || '')] || '待檢查');
  const voiceLabel = value => window.TeacherVoiceCatalog1026?.label?.(value) || '中文語音';
  const note = (text, error) => {
    const node = $('teacher-ai-video-status-1015');
    if (node) {
      node.textContent = text;
      node.className = error ? 'text-xs font-bold text-rose-700' : 'text-xs text-slate-600';
    }
  };
  const busy = value => {
    const button = $('teacher-ai-video-generate-1015');
    if (button) button.disabled = value || !status?.ready || !status?.capabilities?.['video.create'];
  };
  async function api(path, options = {}, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, Object.assign({credentials:'same-origin', cache:'no-store', signal:controller.signal}, options));
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.error || 'AI 影片服務無法回應');
        error.payload = data;
        throw error;
      }
      return data;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('AI 服務回應逾時，已停止這次讀取；請稍後重試。');
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  function rendererPolicyText() {
    const order = status?.rendererPolicy?.order || ['powerpoint-com','libreoffice-headless','text-fallback'];
    return order.map(rendererLabel).join(' → ');
  }
  function syncVoiceOptions(data) {
    const select = $('teacher-ai-video-voice-1015');
    if (!select) return;
    window.TeacherVoiceCatalog1026?.update?.(data || {});
    const source = Array.isArray(data?.voiceOptions) && data.voiceOptions.length
      ? data.voiceOptions
      : (window.TeacherVoiceCatalog1026?.options?.() || []);
    const voices = source
      .map(item => typeof item === 'string' ? {id:item, label:voiceLabel(item)} : item)
      .filter(item => item && item.id);
    if (!voices.length) return;
    const current = select.value;
    select.innerHTML = voices.map(item => '<option value="' + escape(item.id) + '">' + escape(item.label || voiceLabel(item.id)) + '</option>').join('');
    if (voices.some(item => item.id === current)) select.value = current;
    else if (voices.some(item => item.id === data?.defaultVoice)) select.value = data.defaultVoice;
  }

  function renderVoiceHealth(data) {
    const host = $('teacher-ai-video-voice-health-1015');
    if (!host) return;
    const ready = !!data?.readyForPreview;
    if (ready) {
      host.hidden = true;
      host.className = 'hidden';
      host.replaceChildren();
      return;
    }
    host.hidden = false;
    host.className = 'mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[10px] leading-5 text-amber-800';
    const message = data?.enabled === false
      ? 'AI 旁白目前尚未啟用。'
      : 'AI 旁白目前暫時無法使用；請稍後再試。若持續發生，請至 Worker / Job 狀態查看服務狀況。';
    host.innerHTML = `<div class="font-bold">⚠️ ${escape(message)}</div>`;
  }

  async function loadStatus() {
    try {
      const cachedAudioStatus = window.TeacherMediaAudioStatus1014 || null;
      const results = await Promise.all([
        api('/api/ai-videos/status'),
        cachedAudioStatus ? Promise.resolve(cachedAudioStatus) : api('/api/media-audio/status').catch(() => ({}))
      ]);
      status = results[0] || {};
      audioStatus = results[1] || {};
      syncVoiceOptions(audioStatus);
      renderVoiceHealth(audioStatus);
      const provider = $('teacher-ai-video-provider-1015');
      if (provider) {
        provider.textContent = status.ready
          ? 'AI 影片可使用'
          : status.storage?.available
            ? 'AI 影片暫時不可用'
            : 'AI 影片服務尚未啟用';
      }
      const renderer = $('teacher-ai-video-renderer-1015');
      if (renderer) renderer.textContent = status.ready
        ? '品質檢查與教師核准後才能發布'
        : '目前無法建立 AI 影片';
      busy(false);
    } catch (error) {
      note(error.message, true);
    }
  }
  function qualityBadge(video) {
    const manifest = video.qualityManifest || {};
    const state = manifest.status || 'warning';
    const count = state === 'error' ? Number(manifest.errorCount || 0) : Number(manifest.warningCount || 0);
    const cls = state === 'error' ? 'bg-rose-100 text-rose-800' : state === 'warning' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800';
    return `<span class="rounded-full px-2 py-1 text-[11px] font-black ${cls}">${escape(qualityLabel(state))}${count ? ` ${count}` : ''}</span>`;
  }
  function videoCard(video) {
    const metrics = video.renderMetrics || {};
    const attempts = Array.isArray(metrics.rendererAttempts) ? metrics.rendererAttempts : [];
    const rendererAttempts = attempts.length ? attempts.map(item => `${rendererLabel(item.renderer)}:${item.status}`).join(' → ') : '—';
    const preview = video.previewUrl ? `<a class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-black text-indigo-700" target="_blank" rel="noopener" href="${escape(video.previewUrl)}">▶ 預覽 MP4</a>` : '<span class="text-slate-500">MP4 尚未就緒</span>';
    const captions = `${video.vttUrl ? `<a class="rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-700" target="_blank" rel="noopener" href="${escape(video.vttUrl)}">VTT</a>` : ''}${video.srtUrl ? `<a class="rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-700" target="_blank" rel="noopener" href="${escape(video.srtUrl)}">SRT</a>` : ''}`;
    const approve = video.status === 'draft' && status?.capabilities?.['video.approve'] ? '<button type="button" data-video-action="approve" class="rounded-lg bg-emerald-700 px-3 py-1.5 font-black text-white">教師核准影片</button>' : '';
    const publish = video.status === 'approved' && status?.capabilities?.['video.publish'] ? '<button type="button" data-video-action="publish" class="rounded-lg bg-violet-700 px-3 py-1.5 font-black text-white">正式發布影片</button>' : '';
    return `<article data-video-id="${escape(video.id)}" class="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2 text-xs">
      <div class="flex flex-wrap items-start justify-between gap-2"><div><b class="text-sm text-slate-950">${escape(video.title || 'AI 教學影片')}</b><p class="text-[11px] text-slate-500">${escape(video.id)}｜r${Number(video.revisionNumber || 1)}｜${escape(video.status || 'draft')}｜${Math.round(Number(video.durationSeconds || 0))} 秒</p></div><div class="flex flex-wrap gap-2">${qualityBadge(video)}<span class="rounded-full bg-indigo-50 px-2 py-1 text-[11px] font-black text-indigo-800">${escape(rendererLabel(video.frameRenderer))}</span></div></div>
      <p class="text-[11px] text-slate-600">Renderer 嘗試：${escape(rendererAttempts)}｜TTS ${Number(metrics.ttsSegmentCount || 0)} 段｜FFmpeg ${Number(metrics.ffmpegSegmentCount || 0)} 段</p>
      <div class="flex flex-wrap items-center gap-2">${preview}${captions}<button type="button" data-video-action="quality" class="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 font-black text-emerald-700">品質／Renderer 詳情</button>${approve}${publish}</div>
      <pre data-video-detail class="hidden overflow-auto rounded-lg bg-slate-900 p-2 text-[11px] text-slate-100"></pre>
    </article>`;
  }
  async function loadVideos() {
    const presentationId = $('teacher-ai-video-presentation-1015')?.value.trim();
    const list = $('teacher-ai-video-results-1015');
    if (!list) return;
    if (!presentationId) {
      list.textContent = '請先選擇已核准 PowerPoint revision。';
      return;
    }
    try {
      const data = await api(`/api/ai-presentations/${encodeURIComponent(presentationId)}/videos`);
      const videos = data.videos || [];
      list.innerHTML = videos.length ? videos.map(videoCard).join('') : '<p class="text-xs text-slate-500">這個 PowerPoint revision 尚無影片版本。</p>';
    } catch (error) {
      note(error.message, true);
    }
  }
  async function watch(jobId, token) {
    for (let attempt = 0; attempt < 600 && active === jobId && poll === token; attempt += 1) {
      const data = await api(`/api/ai-videos/jobs/${encodeURIComponent(jobId)}`);
      const progress = data.progress || {};
      note(`${progress.stage || data.status || 'AI 影片處理中'}｜${Math.round(Number(progress.percent || 0))}%${progress.detail ? `｜${progress.detail}` : ''}`);
      if (data.status === 'completed') {
        active = '';
        busy(false);
        note('✅ MP4 已保存並完成 Phase 6 品質檢查；請預覽後由授課教師核准。');
        await loadVideos();
        return;
      }
      if (data.status === 'failed') {
        const failure = String(data.error || '未知錯誤');
        const deterministic = /Entry Not Found|\/voices\/|Kokoro 音色|voice.*(?:not found|404)|404.*voice/i.test(failure);
        if (!deterministic && confirm('AI 影片工作失敗：' + failure + '\n\n是否使用同一個工作進行安全重試？')) {
          const retried = await api(`/api/ai-videos/jobs/${encodeURIComponent(jobId)}/retry`, {method:'POST'});
          note(`已重新排入 AI Worker｜attempts ${Number(retried.attempts || 0)}`);
          await new Promise(resolve => setTimeout(resolve, 1500));
          continue;
        }
        throw new Error(failure || 'AI 影片產生失敗');
      }
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    if (active === jobId && poll === token) throw new Error('影片工作等待逾時；可稍後按「讀取版本」確認結果。');
  }
  async function generate() {
    const presentationId = $('teacher-ai-video-presentation-1015')?.value.trim();
    if (!presentationId) return note('請先選擇已準備好的影片畫面來源。', true);
    if (!status?.ready) return note(status?.diagnostic?.message || 'AI Worker／Kokoro 尚未就緒，暫不能建立影片。', true);
    if (!confirm(`確定建立 AI 教學影片嗎？\n\nRenderer 順序：${rendererPolicyText()}\n\n若主要畫面版本不可用，Worker 會自動改用 LibreOffice。完成後仍需教師預覽與核准。`)) return;
    busy(true);
    try {
      const data = await api('/api/ai-videos/generate', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({presentationId, voice:$('teacher-ai-video-voice-1015')?.value || ''})
      });
      active = data.jobId;
      if (!active) throw new Error('伺服器未回傳影片工作 ID');
      await watch(active, ++poll);
    } catch (error) {
      active = '';
      busy(false);
      note(`AI 影片產生失敗：${error.message}`, true);
    }
  }
  async function previewNarrationVoice() {
    const voice = $('teacher-ai-video-voice-1015')?.value || '';
    const button = $('teacher-ai-video-voice-preview-1015');
    const player = $('teacher-ai-video-voice-player-1015');
    if (!voice) return note('請先選擇要試聽的旁白聲音。', true);

    // A prepared preview must be started by a real click. Browsers can block
    // delayed autoplay after the Worker/R2 round-trip, so do not hide that error.
    if (player?.dataset.previewUrl && player.dataset.previewVoice === voice) {
      player.src = player.dataset.previewUrl;
      player.hidden = false;
      try {
        await player.play();
        note('▶ 正在播放旁白聲音試聽。');
      } catch (error) {
        note(`試聽檔案已準備完成，請使用下方播放器按播放。瀏覽器訊息：${error?.message || '自動播放被阻擋'}`, true);
      }
      return;
    }

    if (button) button.disabled = true;
    note('正在準備旁白聲音試聽…');
    try {
      const job = await api('/api/media-audio/preview', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({voice})
      });
      let progress = job;
      if (job.status !== 'completed' && !job.jobId) throw new Error('伺服器未回傳語音試聽工作 ID');
      if (job.reusedActive) note('前一次相同聲音的試聽仍在處理，已接續等待，不會重複建立工作。');
      for (let attempt = 0; attempt < 120; attempt += 1) {
        if (progress.status !== 'completed') {
          progress = await api(`/api/media-audio/jobs/${encodeURIComponent(job.jobId)}`);
        }
        if (progress.status === 'completed') {
          const url = progress.result?.previewUrl;
          if (!url) throw new Error('語音試聽已完成，但暫時沒有可播放檔案');
          let started = false;
          if (player) {
            player.pause?.();
            player.src = url;
            player.dataset.previewUrl = url;
            player.dataset.previewVoice = voice;
            player.hidden = false;
            player.load?.();
            try {
              await player.play();
              started = true;
            } catch (_) {
              // The first preview may finish after the browser's user-gesture
              // autoplay window. Keep the native player visible as the safe fallback.
            }
          }
          if (button) button.textContent = '▶ 播放試聽';
          note(started
            ? '▶ 正在播放旁白聲音試聽。'
            : '✅ 試聽檔案已準備完成；若瀏覽器未自動播放，請按「播放試聽」或下方播放器。');
          return;
        }
        if (progress.status === 'failed') throw new Error(progress.error || '語音試聽失敗');
        const detail = progress.progress || {};
        note(`${detail.stage || 'AI 語音試聽處理中…'}｜${Math.round(Number(detail.percent || 0))}%${detail.detail ? `｜${detail.detail}` : ''}`);
        await new Promise(resolve => setTimeout(resolve, 700));
      }
      throw new Error('本機 AI Worker 尚未完成試聽；已停止持續讀取，請確認 Worker 在線後再試。');
    } catch (error) {
      const blocked = Boolean(
        error?.payload?.workerOffline
        || error?.payload?.workerCapabilityMissing
        || error?.payload?.kokoroUnavailable
      );
      note(blocked
        ? '旁白試聽目前不可用；請依上方 AI Worker／Kokoro 狀態提示處理。'
        : `旁白聲音試聽失敗：${error.message}`, true);
    } finally {
      if (button) button.disabled = false;
    }
  }
  async function videoAction(event) {
    const button = event.target.closest('[data-video-action]');
    if (!button) return;
    const card = button.closest('[data-video-id]');
    const videoId = card?.dataset.videoId;
    if (!videoId) return;
    try {
      if (button.dataset.videoAction === 'quality') {
        const data = await api(`/api/ai-videos/${encodeURIComponent(videoId)}/quality`);
        const output = card.querySelector('[data-video-detail]');
        output.textContent = JSON.stringify({quality:data.quality, frameRenderer:data.frameRenderer, renderMetrics:data.renderMetrics, rendererPolicy:data.rendererPolicy}, null, 2);
        output.classList.toggle('hidden');
        return;
      }
      if (button.dataset.videoAction === 'approve') {
        if (!confirm('確認已完整預覽 MP4、字幕與 renderer 品質，並以授課教師身分核准此影片嗎？')) return;
        await api(`/api/ai-videos/${encodeURIComponent(videoId)}/approve`, {method:'POST'});
        note('✅ 影片已由授課教師核准。');
        await loadVideos();
        return;
      }
      if (button.dataset.videoAction === 'publish') {
        const check = await api(`/api/ai-videos/${encodeURIComponent(videoId)}/quality`);
        if (check.quality?.status === 'error') throw new Error('影片仍有 blocking quality error，不能發布。');
        let acknowledgeWarnings = false;
        if (check.quality?.status === 'warning') {
          const codes = (check.quality.warnings || []).map(item => item.code).join('、');
          if (!confirm(`此影片有品質警告：${codes || '請人工確認'}。\nRenderer：${rendererLabel(check.frameRenderer)}\n\n確認已預覽並仍要正式發布嗎？`)) return;
          acknowledgeWarnings = true;
        } else if (!confirm('確認將此已核准影片建立不可變的正式發布 receipt 嗎？')) return;
        const published = await api(`/api/ai-videos/${encodeURIComponent(videoId)}/publish`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({acknowledgeWarnings})
        });
        const materialVersion=Number(published.materialDerivative?.materialVersion||0);
        note(`✅ AI 影片已正式發布；publication receipt、來源 PPT checksum${materialVersion?'，以及教材 V'+materialVersion+' 衍生內容歷程':''}已保存。`);
        try {
          const pv = published.video || {};
          window.dispatchEvent(new CustomEvent('teacher-ai-video-published', {detail: {
            videoId: String(videoId),
            materialId: String(published.materialDerivative?.materialId || pv.materialId || ''),
            title: String(pv.title || 'AI 教學影片'),
          }}));
        } catch (_) {}
        await loadVideos();
      }
    } catch (error) {
      note(error.message, true);
    }
  }
  async function openVideoSourceAuthoring(files = []) {
    const opener = window.TeacherAIMediaControls1023?.openVideoSourceWorkspace;
    if (typeof opener !== 'function') {
      note('影片來源工具尚未載入完成，請稍候再試。', true);
      return false;
    }
    const opened = await opener();
    if (opened === false) return false;
    const selected = [...(files || [])].filter(Boolean);
    if (!selected.length) return true;
    const input = $('teacher-ai-material-file-1014');
    const upload = $('teacher-ai-material-upload-1014');
    if (!input || !upload || typeof DataTransfer === 'undefined') {
      note('來源上傳元件尚未完成初始化，請在展開的來源區重新選擇檔案。', true);
      return false;
    }
    const transfer = new DataTransfer();
    selected.forEach(file => transfer.items.add(file));
    input.files = transfer.files;
    note(`已接收 ${selected.length} 份來源，正在安全上傳到 R2 並交給 Worker 處理…`);
    upload.click();
    return true;
  }


  function ensureCompactVideoLayout(panel) {
    if (!panel || panel.dataset.simpleFlow1032 === '1') return;
    panel.dataset.simpleFlow1032 = '1';
    const voice = $('teacher-ai-video-voice-1015');
    const generate = $('teacher-ai-video-generate-1015');
    if (!voice || !generate) return;

    const voiceBlock = voice.parentElement;
    const sourceLabel = $('teacher-ai-video-presentation-1015')?.closest('label');
    sourceLabel?.classList.remove('md:col-span-2');
    sourceLabel?.classList.add('md:col-span-3');
    const details = document.createElement('details');
    details.id = 'teacher-ai-video-requirements-1032';
    details.className = 'rounded-xl border border-indigo-100 bg-indigo-50/30 px-3 py-2';
    const summary = document.createElement('summary');
    summary.className = 'cursor-pointer text-xs font-black text-indigo-800';
    summary.textContent = '需求（選填）｜旁白聲音';
    const helper = document.createElement('p');
    helper.className = 'mt-2 text-xs leading-5 text-slate-500';
    helper.textContent = '不選也會使用預設中文旁白。影片內容的語氣與篇幅請在來源整理／PowerPoint 草稿階段調整；最終片長依核准投影片與旁白而定。';
    details.append(summary, helper);
    if (voiceBlock) {
      voiceBlock.classList.add('mt-3');
      details.appendChild(voiceBlock);
    }

    const generateRow = generate.parentElement;
    generateRow?.before(details);
    generate.textContent = '✨ 試產出影片';
  }

  function install() {
    const host = $('teacher-media-production-1014');
    if (!host || $('teacher-ai-video-1015')) return false;
    const panel = document.createElement('section');
    panel.id = 'teacher-ai-video-1015';
    panel.className = 'bg-white border border-indigo-200 rounded-2xl p-5 shadow-sm space-y-4';
    panel.innerHTML = `<div class="flex flex-col lg:flex-row lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-indigo-700">AI VIDEO · F5</p><h4 class="text-lg font-black text-slate-950">🎬 來源內容 + 旁白 → 教學影片</h4><p class="mt-1 text-xs text-slate-500">可從已準備好的簡報開始，也可直接加入 PDF、Word、PPTX、圖片或貼入文字；不必先發布成正式教材。系統需要時會先準備可渲染畫面，再進入旁白、字幕、品質檢查與教師核准。</p></div><div class="flex flex-col items-start lg:items-end gap-2"><span id="teacher-ai-video-provider-1015" class="rounded-full bg-indigo-50 px-3 py-1.5 text-[11px] font-bold text-indigo-800">檢查服務中…</span><span id="teacher-ai-video-renderer-1015" class="text-[11px] font-bold text-slate-600">品質檢查中…</span></div></div><div class="grid md:grid-cols-3 gap-3"><label class="text-xs font-bold text-slate-600 md:col-span-2">影片畫面來源<div class="mt-1 flex flex-col gap-2"><div id="teacher-ai-video-dropzone-1031" class="rounded-xl border-2 border-dashed border-indigo-200 bg-indigo-50/40 px-3 py-3 text-[11px] text-indigo-900" tabindex="0"><div class="flex flex-wrap items-center justify-between gap-2"><span><b>可直接拖曳：</b>PDF／Word／PPTX／Excel／圖片</span><button id="teacher-ai-video-browse-1031" type="button" class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-black text-indigo-700">選擇檔案</button></div><input id="teacher-ai-video-files-1031" type="file" multiple hidden accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odp,.odt,.ods,.txt,.csv,.png,.jpg,.jpeg,.webp"></div><select id="teacher-ai-video-presentation-1015" class="learning-input"><option value="">正在讀取已準備來源…</option></select><div class="flex flex-wrap gap-2"><button id="teacher-ai-video-source-author-1028" type="button" class="rounded-lg bg-indigo-700 px-3 py-2 text-xs font-black text-white">＋ 貼入文字／管理多資料來源</button></div></div><span class="mt-1 block text-[10px] text-slate-500">不強制綁正式教材。直接加入的檔案／文字會先保持為私人製作來源；只有完成教師核准後的可渲染版本才會列入正式影片生成。</span></label><div class="text-xs font-bold text-slate-600">旁白聲音<select id="teacher-ai-video-voice-1015" class="learning-input mt-1"><option value="">讀取可用聲音…</option></select><div class="mt-2 flex flex-wrap items-center gap-2"><button id="teacher-ai-video-voice-preview-1015" type="button" class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs font-black text-indigo-700 disabled:opacity-40">▶ 試聽聲音</button><audio id="teacher-ai-video-voice-player-1015" hidden controls preload="none" class="h-8 max-w-full" aria-label="旁白聲音試聽"></audio></div><div id="teacher-ai-video-voice-health-1015" hidden class="hidden" role="status" aria-live="polite"></div></div></div><div class="flex flex-wrap items-center gap-3"><button id="teacher-ai-video-generate-1015" type="button" class="rounded-xl bg-indigo-700 px-5 py-2.5 text-xs font-black text-white disabled:opacity-40">🎬 建立教學影片</button><button id="teacher-ai-video-refresh-1015" type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-black text-slate-700">讀取影片版本</button><span id="teacher-ai-video-status-1015" class="text-xs text-slate-600">請選擇已準備影片畫面，或直接加入來源資料。</span></div><div id="teacher-ai-video-results-1015" class="space-y-2"></div><div class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] text-amber-900"><b>核准與發布：</b>影片會先以草稿建立；請完成預覽與品質檢查後，由授課教師核准並發布。</div>`;
    host.appendChild(panel);
    ensureCompactVideoLayout(panel);
    panel.addEventListener('click', videoAction);
    $('teacher-ai-video-generate-1015').addEventListener('click', generate);
    $('teacher-ai-video-refresh-1015').addEventListener('click', loadVideos);
    $('teacher-ai-video-source-author-1028')?.addEventListener('click', () => void openVideoSourceAuthoring());
    const sourceFiles = $('teacher-ai-video-files-1031');
    const dropzone = $('teacher-ai-video-dropzone-1031');
    $('teacher-ai-video-browse-1031')?.addEventListener('click', () => sourceFiles?.click());
    sourceFiles?.addEventListener('change', () => {
      const files = [...(sourceFiles.files || [])];
      sourceFiles.value = '';
      if (files.length) void openVideoSourceAuthoring(files);
    });
    dropzone?.addEventListener('dragover', event => {
      event.preventDefault();
      dropzone.classList.add('border-indigo-500', 'bg-indigo-100');
    });
    dropzone?.addEventListener('dragleave', () => {
      dropzone.classList.remove('border-indigo-500', 'bg-indigo-100');
    });
    dropzone?.addEventListener('drop', event => {
      event.preventDefault();
      dropzone.classList.remove('border-indigo-500', 'bg-indigo-100');
      const files = [...(event.dataTransfer?.files || [])];
      if (files.length) void openVideoSourceAuthoring(files);
    });
    $('teacher-ai-video-voice-preview-1015').addEventListener('click', () => void previewNarrationVoice());
    $('teacher-ai-video-voice-1015')?.addEventListener('change', () => {
      const player = $('teacher-ai-video-voice-player-1015');
      const button = $('teacher-ai-video-voice-preview-1015');
      player?.pause?.();
      if (player) {
        player.removeAttribute('src');
        player.hidden = true;
        delete player.dataset.previewUrl;
        delete player.dataset.previewVoice;
        player.load?.();
      }
      if (button) button.textContent = '▶ 試聽聲音';
    });
    $('teacher-ai-video-voice-player-1015').addEventListener('error', () => {
      const player = $('teacher-ai-video-voice-player-1015');
      if (player) {
        delete player.dataset.previewUrl;
        delete player.dataset.previewVoice;
      }
      note('語音檔無法播放，請再按一次「試聽聲音」重新產生。若持續發生，請確認 R2 回應為 audio/wav 且 CSP 允許該網址。', true);
    });
    window.addEventListener('teacher-media-audio-status-1014', event => {
      audioStatus = event.detail?.status || {};
      syncVoiceOptions(audioStatus);
      renderVoiceHealth(audioStatus);
    });
    void loadStatus();
    return true;
  }
  if (!install()) {
    const observer = new MutationObserver(() => { if (install()) observer.disconnect(); });
    observer.observe(document.body, {childList:true, subtree:true});
  }
})();
