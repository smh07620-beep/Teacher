/* AI VIDEO · PHASE 6 renderer contract; product surface is converged into F5. */
/* Teacher video Phase 6 workspace: approved PPT -> resilient renderer -> MP4 -> teacher review/publish. */
(async function () {
  'use strict';
  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  if (!['clinical_teacher','group_leader','education_admin','system_admin'].some(role => roles.has(role))) return;

  let active = '', poll = 0, status = {};
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const rendererLabel = value => ({'powerpoint-com':'Microsoft PowerPoint','libreoffice-headless':'LibreOffice','text-fallback':'安全文字備援'}[String(value || '')] || String(value || '尚未記錄'));
  const qualityLabel = value => ({ok:'品質通過',warning:'品質警告',error:'品質阻擋'}[String(value || '')] || '待檢查');
  const note = (text, error) => {
    const node = $('teacher-ai-video-status-1015');
    if (node) {
      node.textContent = text;
      node.className = error ? 'text-xs font-bold text-rose-700' : 'text-xs text-slate-600';
    }
  };
  const busy = value => {
    const button = $('teacher-ai-video-generate-1015');
    if (button) button.disabled = value || !status?.storage?.available || !status?.capabilities?.['video.create'];
  };
  async function api(path, options) {
    const response = await fetch(path, Object.assign({credentials:'same-origin', cache:'no-store'}, options));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || 'AI 影片服務無法回應');
      error.payload = data;
      throw error;
    }
    return data;
  }
  function rendererPolicyText() {
    const order = status?.rendererPolicy?.order || ['powerpoint-com','libreoffice-headless','text-fallback'];
    return order.map(rendererLabel).join(' → ');
  }
  async function loadStatus() {
    try {
      status = await api('/api/ai-videos/status');
      const provider = $('teacher-ai-video-provider-1015');
      if (provider) {
        provider.textContent = status.storage?.available
          ? '本機 AI｜隱私模式'
          : 'AI 影片服務尚未啟用';
      }
      const renderer = $('teacher-ai-video-renderer-1015');
      if (renderer) renderer.textContent = '品質檢查與教師核准後才能發布';
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
        busy(false);
        note('✅ MP4 已保存並完成 Phase 6 品質檢查；請預覽後由授課教師核准。');
        await loadVideos();
        return;
      }
      if (data.status === 'failed') {
        if (confirm(`AI 影片工作失敗：${data.error || '未知錯誤'}\n\n是否使用同一個工作進行安全重試？`)) {
          const retried = await api(`/api/ai-videos/jobs/${encodeURIComponent(jobId)}/retry`, {method:'POST'});
          note(`已重新排入 AI Worker｜attempts ${Number(retried.attempts || 0)}`);
          await new Promise(resolve => setTimeout(resolve, 1500));
          continue;
        }
        throw new Error(data.error || 'AI 影片產生失敗');
      }
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    if (active === jobId && poll === token) throw new Error('影片工作等待逾時；可稍後按「讀取版本」確認結果。');
  }
  async function generate() {
    const presentationId = $('teacher-ai-video-presentation-1015')?.value.trim();
    if (!presentationId) return note('請填入已核准 PowerPoint revision ID。', true);
    if (!confirm(`確定建立 AI 教學影片嗎？\n\nRenderer 順序：${rendererPolicyText()}\n\n若 PowerPoint 過期或不可用，Worker 會自動改用 LibreOffice。完成後仍需教師預覽與核准。`)) return;
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
      busy(false);
      note(`AI 影片產生失敗：${error.message}`, true);
    }
  }
  async function previewNarrationVoice() {
    const voice = $('teacher-ai-video-voice-1015')?.value || '';
    const button = $('teacher-ai-video-voice-preview-1015');
    const player = $('teacher-ai-video-voice-player-1015');
    if (!voice) return note('請先選擇要試聽的旁白聲音。', true);
    if (button) button.disabled = true;
    note('正在準備旁白聲音試聽…');
    try {
      const job = await api('/api/media-audio/preview', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({voice})
      });
      if (!job.jobId) throw new Error('伺服器未回傳語音試聽工作 ID');
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const progress = await api(`/api/media-audio/jobs/${encodeURIComponent(job.jobId)}`);
        if (progress.status === 'completed') {
          const url = progress.result?.previewUrl;
          if (!url) throw new Error('語音試聽已完成，但暫時沒有可播放檔案');
          if (player) {
            player.src = url;
            player.hidden = false;
            await player.play().catch(() => {});
          }
          note('✅ 旁白聲音試聽已就緒；可在下方播放器重播。');
          return;
        }
        if (progress.status === 'failed') throw new Error(progress.error || '語音試聽失敗');
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
      throw new Error('語音試聽仍在處理，可稍後再試。');
    } catch (error) {
      note(`旁白聲音試聽失敗：${error.message}`, true);
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
        await loadVideos();
      }
    } catch (error) {
      note(error.message, true);
    }
  }
  function install() {
    const host = $('teacher-media-production-1014');
    if (!host || $('teacher-ai-video-1015')) return false;
    const panel = document.createElement('section');
    panel.id = 'teacher-ai-video-1015';
    panel.className = 'bg-white border border-indigo-200 rounded-2xl p-5 shadow-sm space-y-4';
    panel.innerHTML = `<div class="flex flex-col lg:flex-row lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-indigo-700">AI VIDEO · F5</p><h4 class="text-lg font-black text-slate-950">🎬 PowerPoint + 旁白 → 教學影片</h4><p class="mt-1 text-xs text-slate-500">選擇已核准 PowerPoint 與旁白後建立影片；完成後仍需品質檢查、預覽、教師核准與發布。</p></div><div class="flex flex-col items-start lg:items-end gap-2"><span id="teacher-ai-video-provider-1015" class="rounded-full bg-indigo-50 px-3 py-1.5 text-[11px] font-bold text-indigo-800">檢查服務中…</span><span id="teacher-ai-video-renderer-1015" class="text-[11px] font-bold text-slate-600">品質檢查中…</span></div></div><div class="grid md:grid-cols-3 gap-3"><label class="text-xs font-bold text-slate-600 md:col-span-2">已核准 PowerPoint<input id="teacher-ai-video-presentation-1015" class="learning-input mt-1" placeholder="選擇來源後讀取版本"></label><div class="text-xs font-bold text-slate-600">旁白聲音<select id="teacher-ai-video-voice-1015" class="learning-input mt-1"><option value="zf_xiaoxiao">曉曉｜女聲</option><option value="zf_xiaobei">小北｜女聲</option><option value="zf_xiaoni">小妮｜女聲</option><option value="zf_xiaoyi">小藝｜女聲</option><option value="zm_yunxi">雲希｜男聲</option><option value="zm_yunjian">雲健｜男聲</option><option value="zm_yunxia">雲夏｜男聲</option><option value="zm_yunyang">雲揚｜男聲</option></select><div class="mt-2 flex flex-wrap items-center gap-2"><button id="teacher-ai-video-voice-preview-1015" type="button" class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs font-black text-indigo-700 disabled:opacity-40">▶ 試聽聲音</button><audio id="teacher-ai-video-voice-player-1015" hidden controls preload="none" class="h-8 max-w-full" aria-label="旁白聲音試聽"></audio></div></div></div><div class="flex flex-wrap items-center gap-3"><button id="teacher-ai-video-generate-1015" type="button" class="rounded-xl bg-indigo-700 px-5 py-2.5 text-xs font-black text-white disabled:opacity-40">🎬 建立教學影片</button><button id="teacher-ai-video-refresh-1015" type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-black text-slate-700">讀取影片版本</button><span id="teacher-ai-video-status-1015" class="text-xs text-slate-600">請選擇已核准 PowerPoint。</span></div><div id="teacher-ai-video-results-1015" class="space-y-2"></div><div class="rounded-xl border border-amber-100 bg-amber-50 p-3 text-[11px] text-amber-900"><b>核准與發布：</b>影片會先以草稿建立；請完成預覽與品質檢查後，由授課教師核准並發布。</div>`;
    host.appendChild(panel);
    panel.addEventListener('click', videoAction);
    $('teacher-ai-video-generate-1015').addEventListener('click', generate);
    $('teacher-ai-video-refresh-1015').addEventListener('click', loadVideos);
    $('teacher-ai-video-voice-preview-1015').addEventListener('click', () => void previewNarrationVoice());
    void loadStatus();
    return true;
  }
  if (!install()) {
    const observer = new MutationObserver(() => { if (install()) observer.disconnect(); });
    observer.observe(document.body, {childList:true, subtree:true});
  }
})();
